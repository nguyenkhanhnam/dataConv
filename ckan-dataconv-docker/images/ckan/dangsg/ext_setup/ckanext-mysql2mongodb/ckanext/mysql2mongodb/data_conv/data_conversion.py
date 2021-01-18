import sys, json, bson, re, time
from ckanext.mysql2mongodb.data_conv.schema_conversion import SchemaConversion
from ckanext.mysql2mongodb.data_conv.utilities import open_connection_mysql, open_connection_mongodb, import_json_to_mongodb, extract_dict, store_json_to_mongodb, load_mongodb_collection
from bson.decimal128 import Decimal128
from decimal import Decimal
from bson import BSON
from datetime import datetime
from multiprocessing import Pool
from itertools import repeat
	
class DataConversion:
	"""
	DataConversion Database data class.
	This class is used for:
		- Converting and migrating data from MySQL to MongoDB.
		- Validating if converting is correct, using re-converting method.
	"""
	def __init__(self):
		super(DataConversion, self).__init__()

	def set_config(self, schema_conv_init_option, schema_conv_output_option, schema):
		"""
		To set config, you need to provide:
			- schema_conv_init_option: instance of class ConvInitOption, which specified connection to "Input" database (MySQL).
			- schema_conv_output_option: instance of class ConvOutputOption, which specified connection to "Out" database (MongoDB).
			- schema: MySQL schema object which was loaded from MongoDB.
		"""
		self.schema = schema
		#set config
		self.schema_conv_init_option = schema_conv_init_option
		self.schema_conv_output_option = schema_conv_output_option
		self.validated_dbname = self.schema_conv_init_option.dbname + "_validated"

	def run(self):
		self.__save()
		# self.validate()

	def __save(self):
		tic = time.time()
		self.migrate_mysql_to_mongodb()
		toc = time.time()
		time_taken=round((toc-tic)*1000, 1)
		print(f"Time for migrating MySQL to MongoDB: {time_taken}")
		self.validate()
		self.convert_relations_to_references()

	def validate(self):
		"""
		Convert data from MongoDB back to MySQL and evaluate.
		1 Create Database
		2 Create Schema
		3 Define MySQL schema
			3.1 Define tables
			3.2 Define columns of each tables
			3.3 Deinfe constraint
		4 Import data to MySQL
		5 Evaluate 
		"""

		mysql_connection = self.create_validated_database()

		self.create_validated_tables(mysql_connection)
		

		# return

		self.migrate_mongodb_to_mysql(mysql_connection)
		# self.migrate_mongodb_to_mysql(mysql_connection)
		# self.migrate_mongodb_to_mysql(mysql_connection)

		db_schema = self.schema.get()
		table_info_list = self.get_table_info_list()
		for table_info in table_info_list:
			self.alter_one_table(mysql_connection, table_info)

		self.create_triggers(mysql_connection)

		if mysql_connection.is_connected():
			mysql_connection.close()
			print("Disconnected to MySQL Server version ", mysql_connection.get_server_info())


		self.write_validation_log()

	def create_validated_database(self):
		"""
		Create validated database.
		Return connection to new database
		"""
		host = self.schema_conv_init_option.host
		username = self.schema_conv_init_option.username
		password = self.schema_conv_init_option.password
		# validated_dbname = self.schema_conv_init_option.dbname + "_validated"
		mydb = open_connection_mysql(host, username, password)
		mycursor = mydb.cursor()
		mycursor.execute("SHOW DATABASES")
		# mycursor.execute("SELECT schema_name FROM information_schema.schemata;")
		mysql_table_list = [fetched_data[0] for fetched_data in mycursor]
		# print(mysql_table_list)

		if self.validated_dbname in mysql_table_list:
			mycursor.execute(f"DROP DATABASE {self.validated_dbname}")
		
		# print("DROPPPPPPPPPPPPPPPPPPPPPPPPPPPP")
		# print(self.validated_dbname)
		# print(mysql_table_list)
		
		mycursor.execute(f"CREATE DATABASE {self.validated_dbname}")
		mycursor.close()
		mydb.close()
		print("Disconnected to MySQL Server version ", mydb.get_server_info())
		mydb = open_connection_mysql(host, username, password, self.validated_dbname)
		print("Create validated table successfully!")
		return mydb


	def get_tables_creating_info(self):
		"""
		*Get tables only, not views
		Dict(
			key: <table uuid>, 
			value: Dict(
				key: "schema", value: <table name>,
				key: "name", value: <table name>,
				key: "engine", value: <table engine>,
				key: "charset", value: <table charset>,
			)
		)
		"""
		pass

	def get_constraints_creating_info(self):
		pass

	def get_columns_info(self):
		"""
		List[
			Dict(
				key: "uuid", value: <column uuid>,
				key: "column-name", value: <column name>,
				key: "table-name", value: <table name>,
				key: "column-type", value: <column type>,
				key: "auto-incremented", value: <auto incremented option>,
				key: "nullable", value: <nullable option>,
				key: "default-value", value: <default value>,
				key: "column-width", value: <column width>,
				key: "character-set-name", value: <character set name>,
				key: "collation-name", value: <collation name>,
			)
		]
		"""
		db_schema = self.schema.get()
		columns_info_list = []
		for column_schema in db_schema["all-table-columns"]:
			table_name= column_schema["short-name"].split(".")[0]
			column_info = {
				"uuid": column_schema["@uuid"],
				"column-name": column_schema["name"],
				"table-name": table_name,
				"column-type": column_schema["attributes"]["COLUMN_TYPE"],
				"character-set-name": column_schema["attributes"]["CHARACTER_SET_NAME"],
				"collation-name": column_schema["attributes"]["COLLATION_NAME"],
				"auto-incremented": column_schema["auto-incremented"],
				"nullable": column_schema["nullable"],
				# "default-value": self.get_column_default_value(column_schema),
				"default-value": column_schema["default-value"],
				"column-width": column_schema["width"],
			}
			columns_info_list.append(column_info)
		return columns_info_list


	def get_column_default_value(self, column_schema):
		# print(prefix_suffix_col_dtype_list)
		if column_schema["default-value"] is None:
			return None
		# elif column_schema["colu"]
		# return
		prefix_suffix_col_dtype_list = self.get_prefix_suffix_column_data_types_list()
		prefix = ""
		suffix = ""
		for col_dtype in prefix_suffix_col_dtype_list:
			print(col_dtype)
			if column_schema["column-data-type"] == col_dtype["uuid"]:
				prefix = col_dtype["prefix"]
				suffix = col_dtype["suffix"]
				print(prefix, suffix, column_schema["default-value"])
				res = prefix + column_schema["default-value"] + suffix
				return res
		# if column_schema["name"] == "active":
			# print(column_schema["default-value"])
		return column_schema["default-value"]

	def get_prefix_suffix_column_data_types_list(self):
		db_schema = self.schema.get()
		# Get prefix and suffix of default value
		## Get all column-data-type which have prefix and suffix
		column_data_types_list = []
		for column_schema in db_schema["all-table-columns"]:
			if type(column_schema["column-data-type"]) is dict:
				if "literal-prefix" in column_schema["column-data-type"].keys():
					print(column_schema["column-data-type"])
					prefix = column_schema["column-data-type"]["literal-prefix"]
					print("prefix: ", prefix)
				else:
					prefix = None
				if "literal-suffix" in column_schema["column-data-type"].keys():
					suffix = column_schema["column-data-type"]["literal-suffix"]
				else:
					suffix = None
				if prefix is not None and suffix is not None:
					prefix_suffix_info = {
						"uuid": column_schema["column-data-type"]["@uuid"],
						"prefix": column_schema["column-data-type"]["literal-prefix"], 
						"suffix": column_schema["column-data-type"]["literal-suffix"] 
					}
					column_data_types_list.append(prefix_suffix_info)
		return column_data_types_list

		

	def create_validated_tables(self, mysql_connection):
		db_schema = self.schema.get()
		table_info_list = self.get_table_info_list()
		for table_info in table_info_list:
			self.create_one_table(mysql_connection, table_info)
		# for table_info in table_info_list:
			# self.alter_one_table(mysql_connection, table_info)


	def create_one_table(self, mysql_connection, table_info):
		columns_info_list = list(filter(lambda column_info: column_info["uuid"] in table_info["columns-uuid-list"], self.get_columns_info()))
		primary_key_info = list(filter(lambda index_info: index_info["uuid"] == table_info["primary-key-uuid"], self.get_primary_indexes_info_list()))[0] 

		#sql create column
		sql_creating_columns_cmd = ",\n".join([self.generate_sql_creating_column(column_info) for column_info in columns_info_list])
		#sql create primary key
		sql_creating_key_cmd = self.generate_sql_creating_key(primary_key_info)

		sql_creating_columns_and_key_cmd = sql_creating_columns_cmd + ",\n" + sql_creating_key_cmd 
		#sql create table
		sql_creating_table_cmd = f"""CREATE TABLE {table_info["table-name"]} (\n{sql_creating_columns_and_key_cmd}\n) ENGINE={table_info["engine"]}"""# DEFAULT CHARSET={table_info["table-collation"]};"""
		# print(sql_creating_table_cmd)
		
		# create table
		# if table_info["table-name"] == "staff":
		# print(sql_creating_table_cmd)
		mycursor = mysql_connection.cursor()
		mycursor.execute(sql_creating_table_cmd)
		mycursor.close()

	def alter_one_table(self, mysql_connection, table_info):
		"""
		Add foreign key constraints
		"""
		fk_constraints_list = self.get_table_constraint_info_list(table_info["uuid"])
		# sql creating constraint 
		sql_creating_fk_cmd = ",\n".join(self.generate_sql_foreign_keys_list(fk_constraints_list))
		if len(sql_creating_fk_cmd) > 0:
			sql_altering_table_cmd = f"""ALTER TABLE {table_info["table-name"]} {sql_creating_fk_cmd};"""
			mycursor = mysql_connection.cursor()
			mycursor.execute(sql_altering_table_cmd)
			mycursor.close()

	def generate_sql_creating_column(self, column_info):
		"""
		Generate SQL command for creating column from this column info dict:
		Dict(
				key: "uuid", value: <column uuid>,
				key: "column-name", value: <column name>,
				key: "table-name", value: <table name>,
				key: "column-type", value: <column type>,
				key: "column-width", value: <column width>,
				key: "nullable", value: <nullable option>,
				key: "default-value", value: <default value>,
				key: "auto-incremented", value: <auto incremented option>,
				key: "character-set-name", value: <character set name>,
				key: "collation-name", value: <collation name>,
			)
		"""
		sql_cmd_list = []
		sql_cmd_list.append(column_info["column-name"])
		# creating_data_type = self.parse_mysql_data_type(column_info["column-type"], column_info["column-width"])
		sql_cmd_list.append(column_info["column-type"])
		# sql_cmd_list.append(creating_data_type)
		if column_info["character-set-name"] is not None:
			sql_cmd_list.append(f"""CHARACTER SET {column_info["character-set-name"]}""")
		if column_info["collation-name"] is not None:
			sql_cmd_list.append(f"""COLLATE {column_info["collation-name"]}""")
		if column_info["nullable"] is False:
			sql_cmd_list.append("NOT NULL")
		if column_info["default-value"] is not None:
			if column_info["column-type"][:4] == "enum":
				sql_cmd_list.append(f"""default '{column_info["default-value"]}'""")
			else:
				sql_cmd_list.append(f"""default {column_info["default-value"]}""")
		if column_info["auto-incremented"] is True:
			sql_cmd_list.append("AUTO_INCREMENT")
			# CHARACTER SET utf8mb4 COLLATE utf8mb4_bin
		
		# if column_info["character-set-name"] is not None:
		# 	sql_cmd_list.append(f"""CHARACTER SET {column_info["character-set-name"]}""")
		# if column_info["collation-name"] is not None:
			# sql_cmd_list.append(f"""COLLATE {column_info["collation-name"]}""")

		sql_cmd = " ".join(sql_cmd_list)
		return sql_cmd

	def generate_sql_creating_key(self, primary_key_info):
		"""
		Generate SQL creating key command from primary key info dict like this:
		Dict(
				key: "uuid", value: <index uuid>,
				key: "table-name", value: <table name>,
				key: "columns-uuid-list", value: <columns uuid list>,
				key: "unique", value: <unique option>,
			)
		"""
		coluuid_colname_dict = self.schema.get_columns_dict()
		columns_in_pk_list = [coluuid_colname_dict[col_uuid] for col_uuid in primary_key_info["columns-uuid-list"]]
		sql_creating_key = f"""PRIMARY KEY ({", ".join(columns_in_pk_list)})"""
		return sql_creating_key

	def generate_sql_foreign_keys_list(self, fk_info_list):
		"""
		Return list of SQL command for creating foreign key constraints
		Foreign key info like this:
		Dict(
				"name": <fk name>,
				"column-references": List[
					Dict(
						"fk-uuid": <foreign key column uuid>,
						"pk-uuid": <primary key column uuid>,
					)],
				"delete-rule": <delete rule>,
				"update-rule": <update rule>
			)
		"""
		coluuid_colname_dict = self.schema.get_columns_dict()
		coluuid_tablename_dict = self.schema.get_tables_dict()
		sql_fk_cmd_list = []
		for fk_info in fk_info_list:
			col_ref = fk_info["column-references"][0]
			fk_col = coluuid_colname_dict[col_ref["fk-uuid"]]
			pk_col = coluuid_colname_dict[col_ref["pk-uuid"]]
			pk_tabl = coluuid_tablename_dict[col_ref["pk-uuid"]]
			sql_fk_cmd_list.append(f"""ADD CONSTRAINT {fk_info["name"]} FOREIGN KEY ({fk_col}) REFERENCES {pk_tabl} ({pk_col}) ON DELETE {fk_info["delete-rule"]} ON UPDATE {fk_info["update-rule"]}""")
		return sql_fk_cmd_list

	def parse_mysql_data_type(self, dtype, width):
		"""
		Generate MySQL data type for creating column SQL command.
		Params:
			-dtype: MySQL data type and unsigned option
			-width: length of column
		"""
		mysql_type_list = [
			"ascii", 
			"bigint",
			"binary", 
			"bit", 
			"blob", 
			"boolean",
			"bool", 
			"character", 
			"charset", 
			"char", 
			"datetime", 
			"date", 
			"decimal", 
			"dec", 
			"double", 
			"enum", 
			"fixed",
			"float", 
			"geometrycollection",
			"geometry", 
			"integer", 
			"int", 
			"json"
			"linestring", 
			"longblob",
			"longtext",
			"mediumblob", 
			"mediumint", 
			"mediumtext", 
			"multilinestring", 
			"multipoint", 
			"multipolygon", 
			"point", 
			"polygon",
			"real",
			"set",
			"smallint", 
			"text", 
			"timestamp", 
			"time",
			"tinyblob", 
			"tinyint", 
			"tinytext", 
			"unicode", 
			"varbinary",
			"varchar", 
			"year",
		]
		for mysql_type in mysql_type_list:
			if re.search(f"^{mysql_type}", dtype):
				# Handle enum data type
				if mysql_type == "enum":
					return dtype
				elif mysql_type == "set":
					return dtype
				elif mysql_type == "json":
					return dtype
				else:
					if bool(re.search(f"unsigned$", dtype)):
						unsigned = " unsigned"
					else:
						unsigned = ""
					res = mysql_type + width + unsigned
					return res
		print(dtype, width)
		return None

	def get_table_info_list(self):
		"""
		List[
			Dict(
				key: "uuid", value: <table uuid>,
				key: "table-name", value: <table name>,
				key: "engine", value: <engine>,
				key: "table-collation", value: <table collation>,
				key: "columns-uuid-list", value: <List of columns uuid>,
				key: "primary-key-uuid", value: <primary key uuid>,

			)
		]
		Not be handled yet. Will be handled in next phase:
				key: "foreign key", value: ???,
				key: "table-constraints", value: ???,
				key: "indexes", value: ???, ### may be neccesary or not, because primary key is auto indexed
		"""
		table_info_list = []
		db_schema = self.schema.get()
		for table_schema in db_schema["catalog"]["tables"]:
			if self.get_table_type(table_schema["table-type"]) == "TABLE":
				table_info = {
					"uuid": table_schema["@uuid"],
					"table-name": table_schema["name"],
					"engine": table_schema["attributes"]["ENGINE"],
					# "table-collation": table_schema["attributes"]["TABLE_COLLATION"].split("_")[0],
					"columns-uuid-list": table_schema["columns"],
					"primary-key-uuid": table_schema["primary-key"]
				}
				table_info_list.append(table_info)
		return table_info_list

	def get_table_type(self, table_type):
		"""
		Define table type is TABLE or VIEW.
		Parameter:
			-table_type: table type which was get from schema, either be object or string
		"""
		# Dict(key: <table type uuid>, value: <table type>)
		if type(table_type) is dict:
			return table_type["table-type"]
		else:
			table_type_dict = {}
			db_schema = self.schema.get()
			for table_schema in db_schema["catalog"]["tables"]:
				if type(table_schema["table-type"]) is dict:
					table_type_dict[table_schema["table-type"]["@uuid"]] = table_schema["table-type"]["table-type"]
			return table_type_dict[table_type]

	def get_primary_indexes_info_list(self):
		"""
		Get only index on primary keys of tables. 
		Use for defining primary key when creating table.
		Index info:
			Dict(
				key: "uuid", value: <index uuid>,
				key: "table-name", value: <table name>,
				key: "columns-uuid-list", value: <columns uuid list>,
				key: "unique", value: <unique option>,
			)
		"""
		db_schema = self.schema.get()
		indexes_info_list = []
		for table_schema in db_schema["catalog"]["tables"]:
			for index in table_schema["indexes"]:
				if type(index) is dict:
					if index["name"] == "PRIMARY":
						index_info = {
							"uuid": index["@uuid"],
							"table-name": index["attributes"]["TABLE_NAME"],
							"columns-uuid-list": index["columns"],
							"unique": index["unique"]
						}
						indexes_info_list.append(index_info)
		return indexes_info_list

	def get_table_constraint_info_list(self, table_uuid):
		"""
		Get constraint info list from schema
		List[<foreign key info>]
		"""
		table_constraints_info = []
		foreign_key_list = self.get_foreign_keys_list()
		db_schema = self.schema.get()
		table_schema = list(filter(lambda table_schema: table_schema["@uuid"] == table_uuid, db_schema["catalog"]["tables"]))[0]
		table_constraints_list = list(filter(lambda tbl_constr: type(tbl_constr) is dict, table_schema["table-constraints"]))
		table_constraint_name_list = list(map(lambda tbl_constr: tbl_constr["name"], table_constraints_list))
		res = list(filter(lambda fk_info: fk_info["name"] in table_constraint_name_list, foreign_key_list))
		return res

	def get_foreign_keys_list(self):
		"""
		Get list of foreign keys info list
		List[
			Dict(
				"uuid": <fk uuid>,
				"name": <fk name>,
				"column-references": List[
					Dict(
						"fk-uuid": <foreign key column uuid>,
						"pk-uuid": <primary key column uuid>,
					)],
				"delete-rule": <delete rule>,
				"update-rule": <update rule>
			)
		]
		"""
		db_schema = self.schema.get()
		fk_keys_list = []
		for table_schema in db_schema["catalog"]["tables"]:
			for fk_schema in table_schema["foreign-keys"]:
				if type(fk_schema) is dict:
					col_refs = []
					for col_ref in fk_schema["column-references"]:
						col_refs.append({
							"fk-uuid": col_ref["foreign-key-column"],
							"pk-uuid": col_ref["primary-key-column"],
							})
					fk_info = {
						# "uuid": fk_schema["@uuid"],
						"name": fk_schema["name"],
						"delete-rule": fk_schema["delete-rule"],
						"update-rule": fk_schema["update-rule"],
						"column-references": col_refs
					}
					fk_keys_list.append(fk_info)
		return fk_keys_list

	def create_triggers(self, mysql_connection):
		"""
		Create MySQL triggers
		"""
		triggers_info_list = self.get_triggers_info_list()
		for trigger_info in triggers_info_list:
			self.create_one_trigger(mysql_connection, trigger_info)

	def get_triggers_info_list(self):
		"""
		Get list of triggers info.
		List[
			Dict(
				"@uuid" : "6b3c1fdb-52c8-40b0-955f-0cf25a0976ee",
				"table-name": <table name>,
		        "name" : "upd_film",
		        "action-orientation" : "row",
		        "action-statement" : "BEGIN\n    IF (old.title != new.title) OR (old.description != new.description) OR (old.film_id != new.film_id)\n    THEN\n        UPDATE film_text\n            SET title=new.title,\n                description=new.description,\n                film_id=new.film_id\n        WHERE film_id=old.film_id;\n    END IF;\n  END",
		        "condition-timing" : "after",
		        "event-manipulation-type" : "update",
			)
		]
		"""
		db_schema = self.schema.get()
		triggers_info_list = []
		for table_schema in db_schema["catalog"]["tables"]:
			for trigger in table_schema["triggers"]:
				if type(trigger) is dict:
					trigger_info = {
						"uuid": trigger["@uuid"],
						"table-name": table_schema["name"],
						"trigger-name": trigger["name"],
						"action-orientation": trigger["action-orientation"],
						"action-statement": trigger["action-statement"],
						"condition-timing": trigger["condition-timing"],
						"event-manipulation-type": trigger["event-manipulation-type"],
					}
					triggers_info_list.append(trigger_info)
		return triggers_info_list

	def create_one_trigger(self, mysql_connection, trigger_info):
		"""
		"""
		sql_create_trigger = f"""CREATE TRIGGER {trigger_info["trigger-name"]} {trigger_info["condition-timing"]} {trigger_info["event-manipulation-type"]} ON {trigger_info["table-name"]} FOR EACH {trigger_info["action-orientation"]} {trigger_info["action-statement"]}"""
		# print(sql_create_trigger)
		mycursor = mysql_connection.cursor()
		mycursor.execute(sql_create_trigger)
		mycursor.close()


	def migrate_mongodb_to_mysql(self, mysql_connection):
		"""
		Migrate data from MongoDB back to MySQL
		"""
		# for collection_name in self.schema.get_tables_name_list():
		for collection_name in self.schema.get_tables_name_list()[:]:
			self.migrate_one_collection_to_table(mysql_connection, collection_name)

	def migrate_one_collection_to_table(self, mysql_connection, collection_name):
		"""
		Migrate one collection from MongoDB back to MySQL
		"""
		datas = load_mongodb_collection(
			self.schema_conv_output_option.host, 
			self.schema_conv_output_option.username, 
			self.schema_conv_output_option.password, 
			self.schema_conv_output_option.port, 
			self.schema_conv_output_option.dbname, 
			collection_name
		)
		db_schema = self.schema.get()
		col_dict = self.schema.get_columns_dict()
		table_coluuid_list = list(filter(lambda table_schema: table_schema["name"] == collection_name, db_schema["catalog"]["tables"]))[0]["columns"]
		columns_name_list = [col_dict[col_uuid] for col_uuid in table_coluuid_list]
		columns_num = len(columns_name_list)

		columns_name_sql = ["%s"] * columns_num
		cols_info = list(filter(lambda col_inf: col_inf["table-name"] == collection_name, self.get_columns_info()))
		for i in range(len(columns_name_sql)):
			for col_info in cols_info:
				if col_info["column-name"] == columns_name_list[i]:
					if col_info["column-type"][:8] == "geometry":
						columns_name_sql[i] = f"ST_GeomFromText({columns_name_sql[i]})"
						break

		mycursor = mysql_connection.cursor()
		sql = f"""INSERT IGNORE INTO {collection_name} ({", ".join(columns_name_list)}) VALUES ({", ".join(columns_name_sql)})"""
		# val = [[data[key] for key in columns_name_list] for data in datas]
		val = []
		for data in datas:
			row = []
			for key in columns_name_list:
				if key in data.keys():
					dtype = type(data[key])
					if dtype is Decimal128:
						cell_data = data[key].to_decimal()
					elif dtype is list:
						# return
						cell_data = ",".join(data[key])
					elif dtype is dict:
						print(data[key])
						return
					else:
						cell_data = data[key]
				else:
					cell_data = None
				row.append(cell_data)
			val.append(row)
		mycursor.executemany(sql, val)
		mysql_connection.commit()
		print("Insert done!")		


	# def specify_sequence_of_migrating_tables(self):
	# 	"""
	# 	Specify sequence of migrating tables from MySQL. The sequence must guarantee all tables and data within them will be migrated effectively and efficiently.
	# 	We will make a tree to determine which order each table should have.
	# 	Result will be a dictionary which have tables' names as key and orders in sequence as values.
	# 	The lower mark table have, the higher order get, and data of it will be migrate previously.
	# 	"""
	# 	db_schema = self.schema.get()
	# 	tables_schema = db_schema["catalog"]["tables"]
	# 	tables_relations = self.schema.get_tables_relations()
	# 	# print(tables_relations)
	# 	# return
	# 	tables_name_list = self.schema.get_tables_name_list()

	# 	refering_tables_set = set(map(lambda ele: ele["foreign_key_table"], tables_relations.values()))
	# 	root_nodes = set(tables_name_list) - refering_tables_set

	# 	node_seq = dict.fromkeys(tables_name_list, -1)
	# 	node_seq.update(dict.fromkeys(root_nodes, 0))

	# 	# Eliminate self reference relation
	# 	tables_relations_list = list(filter(lambda rel: rel["primary_key_table"] != rel["foreign_key_table"], list(tables_relations.values())))
	# 	# print(tables_relations_list)
	# 	# return
	# 	# print(node_seq)
	# 	current_mark = 0
	# 	lowest_nodes_set = root_nodes 
	# 	current_rels = list(filter(lambda rel: rel["primary_key_table"] in lowest_nodes_set, tables_relations_list))
	# 	print(lowest_nodes_set)
	# 	while len(current_rels) > 0:
	# 		current_mark = current_mark + 1
	# 		lowest_nodes_set = set(map(lambda rel: rel["foreign_key_table"], current_rels))
	# 		print(lowest_nodes_set)
	# 		if(current_mark) == 4:
	# 			return
	# 		for node in lowest_nodes_set:
	# 			node_seq[node] = current_mark
	# 		current_rels = list(filter(lambda rel: rel["primary_key_table"] in lowest_nodes_set, tables_relations_list))
	# 		# print(len(current_rels))
	# 	return


		# def update_seq_list(seq_list, pk_table, fk_table):
		# 	if pk_table in seq_list:
		# 		pk_idx = seq_list.index(pk_table)
		# 		if fk_table in seq_list:
		# 			fk_idx = seq_list.index(fk_table)
		# 			if pk_idx > fk_idx:
		# 				seq_list = swap_seq_list(seq_list, fk_idx, pk_idx)
		# 				seq_list = seq_list[:fk_idx] + seq_list[fk_idx+1:pk_idx+1] + [fk_table] + seq_list[pk_idx+1:] 
		# 		else: 
		# 			seq_list = seq_list[:pk_idx+1] + [fk_table] + seq_list[pk_idx+1:]
		# 	else:
		# 		if fk_table in seq_list:
		# 			fk_idx = seq_list.index(fk_table)	
		# 			seq_list = seq_list[:fk_idx] + [pk_table] + seq_list[fk_idx+1:]
		# 		else:
		# 			seq_list = seq_list + [pk_table, fk_table]
		# 	return seq_list
		# seq_list = list(root_nodes)
		# for rel in tables_relations_list:
		# 	seq_list = update_seq_list(seq_list, rel["primary_key_table"], rel["foreign_key_table"])
		# print(seq_list)
		# return
		# current_mark = 0
		# while(current_mark <= max(node_seq.values())):
		# 	source_nodes = set(filter(lambda key: node_seq[str(key)] == current_mark, node_seq.keys()))
		# 	# print(source_nodes)
		# 	# return
		# 	for source_node in source_nodes:
		# 		for direction in tables_relations_list:
		# 			if(direction["primary_key_table"] == source_node):
		# 				if(node_seq[direction["foreign_key_table"]] < current_mark + 1):
		# 					node_seq[direction["foreign_key_table"]] = current_mark + 1
		# 				direction["primary_key_table"] = None #TODO: Find a more effective way to eliminate retrieved nodes
		# 	current_mark = current_mark + 1
		# print(node_seq)

		# table_seq = {} 
		# for i in range(current_mark):
		# 	table_seq[str(i)] = []
		# 	for key in list(node_seq):
		# 		if node_seq[key] == i:
		# 			table_seq[str(i)] = table_seq[str(i)] + [key]
		# return table_seq 

	def write_validation_log(self):
		"""
		Write validation log to MongoDB
		Dict(
			<key>: <table name>,
			<value>: Dict(
				schema: <schema log>,
				data: <data log>
			)
		)
		"""
		print("Start writing log!")
		# ori_conn = open_connection_mysql(
		# 	self.schema_conv_init_option.host, 
		# 	self.schema_conv_init_option.username, 
		# 	self.schema_conv_init_option.password,
		# 	self.schema_conv_init_option.dbname
		# 	)
		# ori_cur = ori_conn.cursor()

		# val_conn = open_connection_mysql(
		# 	self.schema_conv_init_option.host, 
		# 	self.schema_conv_init_option.username, 
		# 	self.schema_conv_init_option.password,
		# 	self.validated_dbname
		# 	)
		# val_cur = val_conn.cursor()

		mongodb_conn = open_connection_mongodb(
			self.schema_conv_output_option.host,
			self.schema_conv_output_option.username,
			self.schema_conv_output_option.password,
			self.schema_conv_output_option.port, 
			self.schema_conv_output_option.dbname
			)

		# for table in self.schema.get_tables_name_list():
		# 	mongo_count = mongodb_conn[table].count() 
		# 	sql = f"select count(*) from {table};"
		# 	ori_cur.execute(sql)
		# 	val_cur.execute(sql)
		# 	ori_data = ori_cur.fetchall()	
		# 	val_data = val_cur.fetchall()	
		# 	print(ori_data[0][0], mongo_count, val_data[0][0])

		mysql_conn = open_connection_mysql(
			self.schema_conv_init_option.host, 
			self.schema_conv_init_option.username, 
			self.schema_conv_init_option.password,
			)
		mysql_cur = mysql_conn.cursor()

		table_columns_list = self.schema.get_table_column_and_data_type()

		for table_name in self.schema.get_tables_name_list():
			schema_validating_sql = f"""
				SELECT column_name,ordinal_position,data_type,column_type FROM
				(
				    SELECT
				        column_name,ordinal_position,
				        data_type,column_type,COUNT(1) rowcount
				    FROM information_schema.columns
				    WHERE
				    (
				        (table_schema='{self.schema_conv_init_option.dbname}' AND table_name='{table_name}') OR
				        (table_schema='{self.validated_dbname}' AND table_name='{table_name}')
				    )
				    GROUP BY
				        column_name,ordinal_position,
				        data_type,column_type
				    HAVING COUNT(1)=1
				) A;
			"""

			columns_of_table = list(table_columns_list[table_name])
			columns_sql = ",".join(columns_of_table)

			data_validating_sql = f"""
				select {columns_sql}
				from
				(
					SELECT * FROM {self.schema_conv_init_option.dbname}.{table_name} as A
					union all
					SELECT * FROM {self.validated_dbname}.{table_name} as B
				) as C
				group by {columns_sql}
				having count(*) = 1
			"""

			log_data = {}
			log_data["table-name"] = table_name

			mysql_cur.execute(schema_validating_sql)
			schema_validating_data = mysql_cur.fetchall()
			log_data["schema"] = schema_validating_data

			mysql_cur.execute(data_validating_sql)
			data_validating_data = mysql_cur.fetchall()
			log_data["data"] = data_validating_data

			store_json_to_mongodb(mongodb_conn, "validating_log", log_data)

		mysql_cur.close()
		mysql_conn.close()
		print("Writing log done!")


	def find_converted_dtype(self, mysql_dtype):
		"""
		Mapping data type from MySQL to MongoDB.
		Just use this function for migrate_mysql_to_mongodb function
		"""
		mongodb_dtype = {
			"integer": "integer",
			"decimal": "decimal",
			"double": "double",
			"boolean": "boolean",
			"date": "date",
			"timestamp": "timestamp",
			"binary": "binary",
			"blob": "blob",
			"string": "string",
			"object": "object",
			"single-geometry": "single-geometry",
			"multiple-geometry": "multiple-geometry",
		}
		
		dtype_dict = {}
		dtype_dict[mongodb_dtype["integer"]] = ["TINYINT", "SMALLINT", "MEDIUMINT", "INT", "INTEGER", "BIGINT"]
		dtype_dict[mongodb_dtype["decimal"]] = ["DECIMAL", "DEC", "FIXED"]
		dtype_dict[mongodb_dtype["double"]] = ["FLOAT", "DOUBLE", "REAL"]
		dtype_dict[mongodb_dtype["boolean"]] = ["BOOL", "BOOLEAN"]
		dtype_dict[mongodb_dtype["date"]] = ["DATE", "YEAR"]
		dtype_dict[mongodb_dtype["timestamp"]] = ["DATETIME", "TIMESTAMP", "TIME"]
		dtype_dict[mongodb_dtype["binary"]] = ["BIT", "BINARY", "VARBINARY"]
		dtype_dict[mongodb_dtype["blob"]] = ["TINYBLOB", "BLOB", "MEDIUMBLOB", "LONGBLOB"]
		dtype_dict[mongodb_dtype["string"]] = ["CHARACTER", "CHARSET", "ASCII", "UNICODE", "CHAR", "VARCHAR", "TINYTEXT", "TEXT", "MEDIUMTEXT", "LONGTEXT"]
		dtype_dict[mongodb_dtype["object"]] = ["ENUM", "SET", "JSON"]
		dtype_dict[mongodb_dtype["single-geometry"]] = ["GEOMETRY", "POINT", "LINESTRING", "POLYGON"]
		dtype_dict[mongodb_dtype["multiple-geometry"]] = ["MULTIPOINT", "MULTILINESTRING", "MULTIPOLYGON", "GEOMETRYCOLLECTION"]

		for target_dtype in dtype_dict.keys():
			if(mysql_dtype) in dtype_dict[target_dtype]:
				return mongodb_dtype[target_dtype]
		return None 

	def migrate_mysql_to_mongodb(self):
		"""
		Migrate data from MySQL to MongoDB.
		"""
		for table in self.schema.get_tables_name_list():
			self.migrate_one_table_to_collection(table)
		# table_name_list = self.schema.get_tables_name_list()
		# with Pool() as pool:
		# 	pool.map(self.migrate_one_table_to_collection, table_name_list)
		# 	pool.close()
		# 	pool.join()


		
	def migrate_one_table_to_collection(self, table_name):
		fetched_data_list = self.get_fetched_data_list(table_name)
		convert_data_list = self.store_fetched_data_to_mongodb(table_name, fetched_data_list)
		mongodb_connection = open_connection_mongodb(
			self.schema_conv_output_option.host,
			self.schema_conv_output_option.username,
			self.schema_conv_output_option.password,
			self.schema_conv_output_option.port, 
			self.schema_conv_output_option.dbname
			)
		store_json_to_mongodb(mongodb_connection, table_name, convert_data_list)
		
	def get_fetched_data_list(self, table_name):
		colname_coltype_dict = self.schema.get_table_column_and_data_type()[table_name]
		try:
			db_connection = open_connection_mysql(
				self.schema_conv_init_option.host, 
				self.schema_conv_init_option.username, 
				self.schema_conv_init_option.password, 
				self.schema_conv_init_option.dbname, 
			)
			if db_connection.is_connected():
				# col_fetch_seq = []
				sql_cmd = "SELECT"
				for col_name in colname_coltype_dict.keys():
					# col_fetch_seq.append(col_name)
					dtype = colname_coltype_dict[col_name]
					target_dtype = self.find_converted_dtype(dtype)

					# Generating SQL for selecting from MySQL Database
					if target_dtype is None:
						raise Exception(f"Data type {dtype} has not been handled!")
					elif target_dtype == "single-geometry":
						sql_cmd = sql_cmd + " ST_AsText(" + col_name + "),"
					else:
						sql_cmd = sql_cmd + " `" + col_name + "`,"
				#join sql
				sql_cmd = sql_cmd[:-1] + " FROM " + table_name
				db_cursor = db_connection.cursor();
				#execute sql
				db_cursor.execute(sql_cmd)
				#fetch data and convert
				fetched_data = db_cursor.fetchall()
				db_cursor.close()
				return fetched_data 
			else:
				print("Connect fail!")
		
		except Exception as e:
			print("Error while writing to MongoDB", e)
		
		finally:
			if (db_connection.is_connected()):
				db_connection.close()
				print("MySQL connection is closed!")


	def store_fetched_data_to_mongodb(self, table_name, fetched_data):
		"""
		Parallel
		"""
		colname_coltype_dict = self.schema.get_table_column_and_data_type()[table_name]
		rows = []
		### Parallel start from here
		for row in fetched_data:
			data = {}
			col_fetch_seq = list(colname_coltype_dict.keys())
			for i in range(len(col_fetch_seq)):
				col = col_fetch_seq[i]
				dtype = colname_coltype_dict[col]
				target_dtype = self.find_converted_dtype(dtype)
				#generate SQL
				cell_data = row[i]
				if cell_data != None:
					# if dtype == "GEOMETRY":
					# 	geodata = [float(num) for num in cell_data[6:-1].split()]
					# 	geo_x, geo_y = geodata[:2]
					# 	if geo_x > 180 or geo_x < -180:
					# 		geo_x = 0
					# 	if geo_y > 90 or geo_y < -90:
					# 		geo_y = 0
					# 	converted_data = {
					# 		"type": "Point",
					# 		"coordinates": [geo_x, geo_y]
					# 	}
					if dtype == "GEOMETRY":
						converted_data = cell_data
					if dtype == "VARBINARY":
						# print(type(cell_data), str(cell_data))
						converted_data = bytes(cell_data)
						# print(type(converted_data), converted_data)
						# return
					elif dtype == "VARCHAR":
						# print(str[cell_data], type(cell_data))
						# return
						converted_data = str(cell_data)
					elif dtype == "BIT":
						###get col type from schema attribute 
						# mysql_col_type = self.schema.get_col_type_from_schema_attribute(table, col)
						# if mysql_col_type == "tinyint(1)":
						# 	binary_num = cell_data
						# 	converted_data = binary_num.to_bytes(len(str(binary_num)), byteorder="big")
						# else:
						# 	converted_data = cell_data
						converted_data = cell_data
					# elif dtype == "YEAR":
						# print(cell_data, type(cell_data))
					elif dtype == "DATE":
						# print(cell_data, type(cell_data))
						converted_data = datetime(cell_data.year, cell_data.month, cell_data.day)#, cell_data.hour, cell_data.minute, cell_data.second)
					# elif dtype == "JSON":
						# print(type(cell_data), cell_data)
						# return
					# elif dtype == "BLOB":
						# print(cell_data, type(cell_data))
						# return
					elif target_dtype == "decimal":
						converted_data = Decimal128(cell_data)
					elif target_dtype == "object":
						if type(cell_data) is str:
							converted_data = cell_data
						else:
							converted_data = tuple(cell_data)
					else:
						converted_data = cell_data
					data[col_fetch_seq[i]] = converted_data 
			rows.append(data)
		### Parallel end here

		#assign to obj
		#store to mongodb
		# print("Start migrating table ", table)
		return rows

	# def migrate_json_to_mongodb(self):
	# 	"""
	# 	Migrate data from json file to MongoDB.
	# 	"""
	# 	db_connection = open_connection_mongodb(self.schema_conv_output_option.host, self.schema_conv_output_option.port, self.schema_conv_output_option.dbname)
	# 	tables_and_views_name_list = self.schema.get_tables_and_views_list()
	# 	for table_name in tables_and_views_name_list:
	# 		collection_name = table_name
	# 		json_filename = collection_name + ".json"
	# 		import_json_to_mongodb(db_connection, collection_name, self.schema_conv_output_option.dbname, json_filename, True)
	# 	print("Migrate data from JSON to MongoDB successfully!")

	def convert_relations_to_references(self):
		"""
		Convert relations of MySQL table to database references of MongoDB
		"""
		tables_name_list = self.schema.get_tables_name_list()
		# db_connection = open_connection_mongodb(mongodb_connection_info)
		tables_relations = self.schema.get_tables_relations()
		# converting_tables_order = specify_sequence_of_migrating_tables(schema_file)
		edited_table_relations_dict = {}
		original_tables_set = set([tables_relations[key]["primary_key_table"] for key in tables_relations])

		# Edit relations of table dictionary
		for original_table in original_tables_set:
			for key in tables_relations:
				if tables_relations[key]["primary_key_table"] == original_table:
					if original_table not in edited_table_relations_dict.keys():
						edited_table_relations_dict[original_table] = []
					edited_table_relations_dict[original_table] = edited_table_relations_dict[original_table] + [extract_dict(["primary_key_column", "foreign_key_table", "foreign_key_column"])(tables_relations[key])]
		# Convert each relation of each table
		for original_collection_name in tables_name_list:
			if original_collection_name in original_tables_set:
				for relation_detail in edited_table_relations_dict[original_collection_name]:
					referencing_collection_name = relation_detail["foreign_key_table"]
					original_key = relation_detail["primary_key_column"]
					referencing_key = relation_detail["foreign_key_column"]
					self.convert_one_relation_to_reference(original_collection_name, referencing_collection_name, original_key, referencing_key) 
		print("Convert relations successfully!")


	def convert_one_relation_to_reference(self, original_collection_name, referencing_collection_name, original_key, referencing_key):
		"""
		Convert one relation of MySQL table to database reference of MongoDB
		"""
		db_connection = open_connection_mongodb(
			self.schema_conv_output_option.host,
			self.schema_conv_output_option.username,
			self.schema_conv_output_option.password,
			self.schema_conv_output_option.port, 
			self.schema_conv_output_option.dbname
			)
		original_collection_connection = db_connection[original_collection_name]
		original_documents = original_collection_connection.find()
		new_referenced_key_dict = {}
		for doc in original_documents:
			new_referenced_key_dict[doc[original_key]] = doc["_id"]

		referencing_documents = db_connection[referencing_collection_name]
		for key in new_referenced_key_dict:
			new_reference = {}
			new_reference["$ref"] = original_collection_name
			new_reference["$id"] = new_referenced_key_dict[key]
			new_reference["$db"] = self.schema_conv_output_option.dbname
			referencing_key_new_name = "db_ref_" + referencing_key
			referencing_documents.update_many({referencing_key: key}, update={"$set": {referencing_key_new_name: new_reference}})

	
