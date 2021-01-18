# database_config.py: Classes which are used for construct database connection

class ConvInitOption:
	"""
	Class Conversion Initialized Connection Option.
	This class is usually used for MySQL connection.
	"""
	def __init__(self, host, username, password, port, dbname):
		super(ConvInitOption, self).__init__()
		self.host = host
		self.username = username
		self.password = password
		self.port = port
		# self.dbtype = dbtype = "MySQL"
		self.dbname = dbname

class ConvOutputOption:
	"""
	Class Conversion Output Connection Option.
	This class is usually used for MongoDB connection.
	"""
	def __init__(self, host, username, password, port, dbname):
		super(ConvOutputOption, self).__init__()
		self.host = host
		self.username = username
		self.password = password
		self.port = port
		# self.dbtype = dbtype = "MongoDB"
		self.dbname = dbname		
		