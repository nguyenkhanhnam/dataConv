import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
from ckanext.mysql2mongodb.data_conv.main import convert_data
import pprint, os

class Mysql2MongodbPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IResourceController)

    def after_create(self, context, resource):
        #pprint.pprint(context)
        #pprint.pprint(resource)
        # os.system("pwd")
        # os.system("whoami")
        sql_file_name = resource["name"]
        sql_file_url = resource["url"]
        resource_id = resource["id"]
        # pprint.pprint(f"{resource_id}")
        # pprint.pprint(f"{sql_file_name}") 
        # pprint.pprint(f"{sql_file_url}")
        toolkit.enqueue_job(convert_data, [resource_id, sql_file_name, sql_file_url])

    def before_create(self, context, resource):
    	pass

    def before_update(self, context, current, resource):
    	pass

    def after_update(self, context, resource):
    	pass

    def before_delete(self, context, resource, resources):
    	pass

    def after_delete(self, context, resources):
    	pass

    def before_show(self, resource_dict):
    	pass
    

