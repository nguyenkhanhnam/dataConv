from logging import getLogger


def my_log_info():
	log = getLogger(__name__)
	log.info("""
			*
			**
			***
			Resource was created successfully!
			***
			**
			*
			""")