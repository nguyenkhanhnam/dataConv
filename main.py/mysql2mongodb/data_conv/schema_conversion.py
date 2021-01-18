import json, os, re
from collections import OrderedDict
from pymongo import GEO2D, TEXT
from ckanext.mysql2mongodb.data_conv.utilities import extract_dict, import_json_to_mongodb, open_connection_mongodb, open_connection_mysql, drop_mongodb_database, load_mongodb_collection, store_json_to_mongodb
	
class SchemaConversion:
	"""
	MySQL Database Schema class.
	This class is used for
		- Extracting schema from MySQL database. 
		- Exporting MySQL schema as JSON.
		- Storing MySQL schema as a collection in MongoDB database.
		- Loading MySQL schema, which was stored in MongoDB before, for another processes.
		- Defining a MongoDB schema validator based on MySQL schema.
		- Creating MongoDB secondary indexes based on MySQL schema.
	All above processes are belong to phase "Schema Conversion".
	"""

	def __init__(self):
		super(SchemaConversion, self).__init__()
		# Define a name for schema file, which will be place at intermediate folder.
		self.schema_filename = "schema.json"

	def set_config(self, schema_conv_init_option, schema_conv_output_option):
		"""
		To set up connections, you need to provide:
			- schema_conv_init_option:_ instance of class ConvInitOption, which specified connection to "Input" database (MySQL).
			- schema_conv_output_option: instance of class ConvOutputOption, which specified connection to "Out" database (MongoDB).
		"""
		self.schema_conv_init_option = schema_conv_init_option
		self.schema_conv_output_option = schema_conv_output_option

	def run(self):
		self.__drop_mongodb()
		self.__generate_mysql_schema()
		self.__save()
		self.save_schema_view()
		self.create_mongo_schema_validators()
		self.create_mongo_indexes()
		self.drop_view()
		return True

	def get(self):
		self.load_schema()
		return self.db_schema


	def __save(self):
		"""
		Save MySQL schema which was generate by SchemaCrawler to MongoDB database
		"""
		db_connection = open_connection_mongodb(
			self.schema_conv_output_option.host, 
			self.schema_conv_output_option.username, 
			self.schema_conv_output_option.password, 
			self.schema_conv_output_option.port, 
			self.schema_conv_output_option.dbname) 
		# print("Ready 		
		import_json_to_mongodb(db_connection, collection_name="schema", dbname=self.schema_conv_output_option.dbname, json_filename=self.schema_filename)
		print(f"Save schema from {self.schema_conv_output_option.dbname} database to MongoDB successfully!")
		return True
	

	def load_schema(self):
		"""
		Load schema from JSON file.
		*Need to be edited for loading from MongoDB instead.
		"""
		if not hasattr(self, "db_schema"):
			db_schema = load_mongodb_collection(
				self.schema_conv_output_option.host,
				self.schema_conv_output_option.username,
				self.schema_conv_output_option.password, 
				self.schema_conv_output_option.port, 
				self.schema_conv_output_option.dbname, 
				"schema")
			self.db_schema = db_schema[0]
			# Most used variable
			self.all_table_columns = self.db_schema["all-table-columns"]
			self.tables_schema = self.db_schema["catalog"]["tables"]
			self.extracted_tables_schema = self.extract_tables_schema()
	
	def __generate_mysql_schema(self, info_level="maximum"):
		"""
		Generate MySQL schema using SchemaCrawler, then save as JSON file at intermediate directory.
		"""
		command_create_intermediate_dir = f"mkdir -p ./intermediate_data/{self.schema_conv_init_option.dbname}"
		os.system(command_create_intermediate_dir)
		command = f"_schemacrawler/schemacrawler.sh \
		--server=mysql \
		--host={self.schema_conv_init_option.host} \
		--port={self.schema_conv_init_option.port} \
		--database={self.schema_conv_init_option.dbname} \
		--schemas={self.schema_conv_init_option.dbname} \
		--user={self.schema_conv_init_option.username} \
		--password={self.schema_conv_init_option.password} \
		--info-level={info_level} \
		--command=serialize\
		--output-file=./intermediate_data/{self.schema_conv_init_option.dbname}/{self.schema_filename}"
		os.system(command)
		print(f"Generate MySQL database {self.schema_conv_init_option.dbname} schema successfully!")
		return True


	def __drop_mongodb(self):
		"""
		Drop a MongoDB database.
		For development only.
		"""
		drop_mongodb_database(
			self.schema_conv_output_option.host, 
			self.schema_conv_output_option.username, 
			self.schema_conv_output_option.password, 
			self.schema_conv_output_option.port, 
			self.schema_conv_output_option.dbname)

	def drop_view(self):
		mongodb_connection = open_connection_mongodb(
			self.schema_conv_output_option.host,
			self.schema_conv_output_option.username,
			self.schema_conv_output_option.password,
			self.schema_conv_output_option.port, 
			self.schema_conv_output_option.dbname
			)
		view_set = set(self.get_tables_and_views_list()) - set(self.get_tables_name_list())
		for view in list(view_set):
			mycol = mongodb_connection[view]
			mycol.drop() 
		return True

	def extract_tables_schema(self, extracted_keys_list = ["@uuid", "name", "columns", "foreign-keys"]):
		"""
		Extract only specific fields from tables schema.
		Params:
			extracted_keys_list: List of specific keys. 
		""" 
		ite_func = extract_dict(extracted_keys_list)
		return list(map(ite_func, self.tables_schema))	

	def get_columns_dict(self):
		"""
		Extract column uuid and name from database schema
		Return a dictionary with @uuid as key and column name as value
		Dict(key: <column uuid>, value: <column name>)
		"""
		all_table_columns = self.db_schema["all-table-columns"]
		col_dict = {}
		for col in all_table_columns:
			col_dict[col["@uuid"]] = col["name"]
		return col_dict

	def get_tables_dict(self):
		"""
		Extract column uuid and its table name from database schema
		Return a dictionary with @uuid as key and table name as value
		Dict(key: <column uuid>, value: <name of table has that column>)
		"""
		table_dict = {}
		for table in self.tables_schema:
			for col in table["columns"]:
				table_dict[str(col)] = table["name"]
		return table_dict


	def get_tables_relations(self):
		"""
		Get relations between MySQL tables from database schema.
		Result will be a dictionary which has uuids (of relation, defined by SchemaCrawler) as keys, and values including:
		- source: Name of table which holds primary key of relation
		- dest: Name of table which holds foreign key of relation
		Dict(
			key: <relation uuid>,
			values: Dict(
				"primary_key_table": <primary table name>,
				"foreign_key_table": <foreign table name>,
				"primary_key_column": <primary column name>,
				"foreign_key_column": <foreign column name>
			)

		)
		"""
		col_dict = self.get_columns_dict()
		table_dict = self.get_tables_dict()

		relations_dict = {}
		for table in self.extracted_tables_schema:
			for foreign_key in table["foreign-keys"]:
				if(isinstance(foreign_key, dict)):
					relation_uuid = foreign_key["@uuid"]
					foreign_key_uuid = foreign_key["column-references"][0]["foreign-key-column"]
					primary_key_uuid = foreign_key["column-references"][0]["primary-key-column"]
					relations_dict[relation_uuid] = {}
					relations_dict[relation_uuid]["primary_key_table"] = table_dict[primary_key_uuid]
					relations_dict[relation_uuid]["foreign_key_table"] = table_dict[foreign_key_uuid]
					relations_dict[relation_uuid]["primary_key_column"] = col_dict[primary_key_uuid]
					relations_dict[relation_uuid]["foreign_key_column"] = col_dict[foreign_key_uuid]
		return relations_dict

	def get_tables_name_list(self):
		"""
		Get list of name of all tables.
		"""
		self.load_schema()
		table_name_list = list(map(lambda table: table["name"], list(filter(lambda table: table["remarks"] == "", self.tables_schema))))
		return table_name_list

	def get_tables_and_views_list(self):
		"""
		Get list of name of all tables and views.
		"""
		self.load_schema()
		table_and_view_name_list = list(map(lambda table: table["name"], self.extracted_tables_schema))
		return table_and_view_name_list

	def get_table_column_and_data_type(self):
		"""
		Get dict of tables, columns name and columns data type.
		Dict(
			key: <table name>
			value: Dict(
				key: <column name>
				value: <MySQL column data type>
			)
		)
		"""
		self.load_schema()
		table_dict = self.get_tables_dict()
		all_columns = self.db_schema["all-table-columns"]
		schema_type_dict = {}
		for col in all_columns:
			dtype = col["column-data-type"]
			if type(dtype) is dict:
				schema_type_dict[dtype["@uuid"]] = dtype["name"].split()[0]
		table_list = self.get_tables_and_views_list()
		res = {}
		for table_name in table_list:
			res[table_name] = {}
		for col in all_columns:
			dtype = col["column-data-type"]
			if type(dtype) is dict:
				res[table_dict[col["@uuid"]]][col["name"]] = schema_type_dict[dtype["@uuid"]]
			else:
				res[table_dict[col["@uuid"]]][col["name"]] = schema_type_dict[dtype]
		return res

	def create_mongo_schema_validators(self):
		"""
		Specify MongoDB schema validator for all tables.
		"""
		table_view_column_dtype = self.get_table_column_and_data_type()
		table_list = self.get_tables_name_list()
		uuid_col_dict = self.get_columns_dict()
		table_column_dtype = {}
		for table in table_list:
			table_column_dtype[table] = table_view_column_dtype[table]
		table_cols_uuid = {}
		for table in self.tables_schema:
			table_name = table["name"]
			if table_name in table_list:
				table_cols_uuid[table_name] = table["columns"]
		enum_col_dict = {}
		for col in self.all_table_columns:
			if col["attributes"]["COLUMN_TYPE"][:4] == "enum":
				data = {}
				table_name, col_name = col["short-name"].split(".")[:2]
				if table_name in table_list:
					data = list(map(lambda ele: ele[1:-1], col["attributes"]["COLUMN_TYPE"][5:-1].split(",")))
					sub_dict = {}
					sub_dict[col_name] = data
					enum_col_dict[table_name] = sub_dict
		db_connection = open_connection_mongodb(
			self.schema_conv_output_option.host,
			self.schema_conv_output_option.username,
			self.schema_conv_output_option.password,
			self.schema_conv_output_option.port, 
			self.schema_conv_output_option.dbname
			)
		for table in self.get_tables_and_views_list():
			db_connection.create_collection(table)
		for table in table_cols_uuid:
			props = {}
			for col_uuid in table_cols_uuid[table]:
				col_name = uuid_col_dict[col_uuid]
				mysql_dtype = table_column_dtype[table][col_name]
				if mysql_dtype == "ENUM":
					data = {
						"enum": enum_col_dict[table][col_name],
						"description": "can only be one of the enum values"
					}
				else:
					data = {
						"bsonType": self.data_type_schema_mapping(mysql_dtype)
					}
				props[col_name] = data
				json_schema = {}
				json_schema["bsonType"] = "object"
				json_schema["properties"] = props
				# print(json_schema)
				vexpr = {"$jsonSchema": json_schema}
				cmd = OrderedDict([('collMod', table), ('validator', vexpr)])
				db_connection.command(cmd)
		print("Create validator done!")
		

	def data_type_schema_mapping(self, mysql_type):
		"""
		Mapping data type from MySQL to MongoDB.
		Input: MySQL data type.
		Output: MongoDB data type.
		"""
		dtype_dict = {}
		dtype_dict["int"] = ["BIT", "TINYINT", "SMALLINT", "MEDIUMINT", "INT", "INTEGER", "YEAR", "BOOL", "BOOLEAN"] 
		dtype_dict["long"] = ["BIGINT"]
		dtype_dict["decimal"] = ["DECIMAL", "DEC", "FIXED"]
		dtype_dict["double"] = ["FLOAT", "DOUBLE", "REAL"]
		# dtype_dict["bool"] = []
		dtype_dict["date"] = ["DATE", "DATETIME", "TIMESTAMP", "TIME"]
		# dtype_dict["timestamp"] = []
		dtype_dict["binData"] = ["BINARY", "VARBINARY", "TINYBLOB", "BLOB", "MEDIUMBLOB", "LONGBLOB"]
		# dtype_dict["blob"] = []
		dtype_dict["string"] = ["JSON", "CHARACTER", "CHARSET", "ASCII", "UNICODE", "CHAR", "VARCHAR", "TINYTEXT", "TEXT", "MEDIUMTEXT", "LONGTEXT", "GEOMETRY", "POINT", "LINESTRING", "POLYGON", "MULTIPOINT", "MULTILINESTRING", "MULTIPOLYGON", "GEOMETRYCOLLECTION"]
		dtype_dict["object"] = ["ENUM"]
		dtype_dict["array"] = ["SET"]
		# dtype_dict["single-geometry"] = []
		# dtype_dict["multiple-geometry"] = []

		for mongodb_type in dtype_dict.keys():
			if mysql_type in dtype_dict[mongodb_type]:
				# print(mysql_type, mongodb_type)
				return mongodb_type
		print(f"MySQL data type {mysql_type} has not been handled!")
		return None

	def create_mongo_indexes(self):
		"""
		Add index to MongoDB collection.
		Just use for running time. Need to remove indexes before exporting MongoDB database.
		"""
		table_view_list = self.get_tables_and_views_list()
		
		mysql_connection = open_connection_mysql(
			self.schema_conv_init_option.host, 
			self.schema_conv_init_option.username, 
			self.schema_conv_init_option.password, 
			self.schema_conv_init_option.dbname, 
			)
		mysql_cursor = mysql_connection.cursor()
		# Get indexes from MySQL by using SQL command because SchemaCrawler have not get enough information about indexes
		sql_fetch_index = f"SELECT DISTINCT TABLE_NAME, INDEX_NAME, INDEX_TYPE FROM INFORMATION_SCHEMA. STATISTICS;"
		mysql_cursor.execute(sql_fetch_index)
		record = mysql_cursor.fetchall()
		idx_table_name_type_dict = {}
		for row in record:
			table_name, idx_name, idx_type = row
			# print(row)
			if table_name in table_view_list:
				if not table_name in idx_table_name_type_dict:
					# if table_name == "actor":
						# print(idx_table_name_type_dict)
						# print(idx_name)
					idx_table_name_type_dict[table_name] = {}
				idx_table_name_type_dict[table_name][idx_name] = idx_type
		col_dict = self.get_columns_dict()
		mongodb_connection = open_connection_mongodb(
			self.schema_conv_output_option.host,
			self.schema_conv_output_option.username,
			self.schema_conv_output_option.password,
			self.schema_conv_output_option.port, 
			self.schema_conv_output_option.dbname
			) 
		for table in self.tables_schema:
			collection = mongodb_connection[table["name"]]
			index_list = table["indexes"]
			for index in index_list:
				if(type(index) is not str): ### need to check all indexes again
					# print(index)
					if table["name"] in idx_table_name_type_dict:
						index_name = index["name"]
						index_type = idx_table_name_type_dict[table["name"]][index_name]
						index_unique = index["unique"]
						index_cols = index["columns"]
						num_sub_index = len(index_cols)
						if index_type == "BTREE":
							if num_sub_index == 1:
								# mongo_index_type = "default"
								col_name = col_dict[index_cols[0]]
								# print(type(col_name))
								# collection.create_index("idx_" + col_name, unique = index_unique)
								if col_name != "_id":
									collection.create_index(col_name, unique = index_unique)
							else:
								# mongo_index_type = "compound"
								# index_keys = {}
								# for idx_uuid in index_cols:
									# index_keys[col_dict[idx_uuid]] = 1
								collection.create_index([(col_dict[idx_uuid], 1) for idx_uuid in index_cols], unique = index_unique)
						# elif index_type == "SPATIAL":
						# 	# mongo_index_type = "spatial"
						# 	# print(col_dict[index_cols[0]])
						# 	if num_sub_index == 1:
						# 		# collection.create_index([(col_dict[index_cols[0]], GEO2D)], unique = index_unique)
						# 		collection.create_index([(col_dict[index_cols[0]], "2dsphere")], unique = index_unique)
						# 	else:
						# 		collection.create_index([(col_dict[idx_uuid], TEXT) for idx_uuid in index_cols], unique = index_unique)
						# 	pass
						# elif index_type == "FULLTEXT":
						# 	# mongo_index_type = "text-index"
						# 	if num_sub_index == 1:
						# 		collection.create_index(col_dict[index_cols[0]], TEXT, unique = index_unique)
						# 	else:
						# 		collection.create_index([(col_dict[idx_uuid], TEXT) for idx_uuid in index_cols], unique = index_unique)
						# else:
							# print(f"MySQL index type {index_type} has not been handled!")
		


	def get_coluuid(self, table_name, col_name):
		"""
		Get column uuid:
		Input: Table name and column name.
		Output: Column uuid
		"""
		self.load_schema()
		for col in self.all_table_columns():
			if f"{table_name}.{col_name}" == col["short-name"]:
				return col["@uuid"]
		print(f"Can not find column {col_name} from table {table_name}!")
		return None

	def get_col_type_from_schema_attribute(self, table_name, col_name):
		"""
		Get MySQL column data type from schema.
		Input: Table name and column name.
		Output: MySQL data type of column.
		"""
		self.load_schema()
		for col in self.all_table_columns:
			if f"{table_name}.{col_name}" == col["short-name"]:
				return col["attributes"]["COLUMN_TYPE"]
		print(f"Can not find column {col_name} from table {table_name}!")
		return None

	def save_schema_view(self):
		"""
		Store a MySQL converted schema in MongoDB. 
		This schema will be used for generated detail schema in future by end-user.
		Converted schema structure:
			Dict(
				"Converted schema": Dict(
					"Database type": "MySQL",
					"Schema": <Database name>,
					"Tables": List[
						Dict(
							"Table name": <table name>,
							"Columns": List[
								"Column name": <column name>
							]
						)
					]
				)
			)
		"""
		self.load_schema()
		converted_schema = {}
		catalog_schema = self.db_schema["catalog"]

		converted_schema["database-name"] = catalog_schema["database-info"]["product-name"]
		converted_schema["database-version"] = catalog_schema["database-info"]["product-version"]
		converted_schema["schema"] = catalog_schema["name"]
		converted_schema["tables"] = []
		converted_schema["foreign-keys"] = []

		tables_schema = catalog_schema["tables"]
		for table_schema in tables_schema:
			table_info = {}
			table_info["name"] = table_schema["name"]
			table_info["engine"] = table_schema["attributes"]["ENGINE"]
			table_info["table-collation"] = table_schema["attributes"]["TABLE_COLLATION"]

			table_info["constraints"] = []
			for table_schema_constraint in table_schema["table-constraints"]:
				if type(table_schema_constraint) is dict:
					table_constraint = {
						"name": table_schema_constraint["name"],
						"type": table_schema_constraint["constraint-type"],
						"definition": table_schema_constraint["definition"]
					}
					table_info["constraints"].append(table_constraint)

			table_info["triggers"] = []
			for table_schema_trigger in table_schema["triggers"]:
				if type(table_schema_trigger) is dict:
					table_trigger = {
						"name": table_schema_trigger["name"],
						"action-condition" : table_schema_trigger["action-condition"],
						"action-order" : table_schema_trigger["action-order"],
						"action-orientation" : table_schema_trigger["action-orientation"],
						"action-statement" : table_schema_trigger["action-statement"],
						"condition-timing" : table_schema_trigger["condition-timing"],
						"event-manipulation-type" : table_schema_trigger["event-manipulation-type"],
					}
					table_info["triggers"].append(table_trigger)

			columns_schema = self.db_schema["all-table-columns"]
			table_info["columns"] = []
			for column_schema in columns_schema:
				if column_schema["@uuid"] in table_schema["columns"]:
					column_info = {
						"name": column_schema["name"],
						"character-set-name": column_schema["attributes"]["CHARACTER_SET_NAME"],
						"collation-name": column_schema["attributes"]["COLLATION_NAME"],
						"column-type": column_schema["attributes"]["COLUMN_TYPE"],
						"nullable": column_schema["attributes"]["IS_NULLABLE"],
						"auto-incremented": column_schema["auto-incremented"],
						"nullable": column_schema["nullable"],
						"default-value" : column_schema["default-value"],
					}
					table_info["columns"].append(column_info)

			table_info["indexes"] = []
			for index_schema in table_schema["indexes"]:
				if type(index_schema) is dict:
					index_column_list = list(map(lambda col_sche: {"name": col_sche["name"], "table": col_sche["short-name"].split(".")[0]}, list(filter(lambda col_sche: col_sche["@uuid"] in index_schema["columns"], columns_schema))))
					index_info = {
						"name": index_schema["name"],
						"unique": index_schema["unique"],
						"columns": index_column_list
					}
					table_info["indexes"].append(index_info)

			converted_schema["tables"].append(table_info)

			table_dict = self.get_tables_dict()
			cols_dict = self.get_columns_dict()
			for foreign_key_schema in table_schema["foreign-keys"]:
				if type(foreign_key_schema) is dict:
					col_refs = list(map(lambda fk_sche: {
							"key-sequence": fk_sche["key-sequence"],
							"foreign-key-column": cols_dict[fk_sche["foreign-key-column"]], 
							"foreign-key-table": table_dict[fk_sche["foreign-key-column"]],
							"primary-key-column": cols_dict[fk_sche["primary-key-column"]], 
							"primary-key-table": table_dict[fk_sche["primary-key-column"]],
						}, 
						foreign_key_schema["column-references"]))
					foreign_key_info = {
						"name": foreign_key_schema["name"],
						"column-references": col_refs,
						"delete-rule": foreign_key_schema["delete-rule"],
						"update-rule": foreign_key_schema["update-rule"],
					}
					converted_schema["foreign-keys"].append(foreign_key_info)
		
		mongodb_connection = open_connection_mongodb(
			self.schema_conv_output_option.host,
			self.schema_conv_output_option.username,
			self.schema_conv_output_option.password,
			self.schema_conv_output_option.port, 
			self.schema_conv_output_option.dbname
			) 
		store_json_to_mongodb(mongodb_connection, "schema_view", converted_schema)
		print(f"Save schema view from {self.schema_conv_output_option.dbname} database to MongoDB successfully!")
		return True