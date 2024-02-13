import json
import logging
import requests
from datetime import datetime
 
logger = logging.getLogger(__name__)
 
OK_STATUS_CODES = (200)

Jira_ID = 'name' 
Jira_Passsword = 'pwd' 
class LassoTokenClient:
 
    # Initialize LASSO Token Client
    def __init__(self, lasso_token_url, username, password, service):
        self.lasso_token_url = lasso_token_url
        self.username = username
        self.password = password
        self.service = service
        self.get_new_access_token()
 
    # Retrieve new LASSO access token using bot username/password and save it
    def get_new_access_token(self):
        headers = {"Content-Type": "application/json"}
        data = {"username": self.username, "password": self.password, "service": self.service}
        res = requests.post(self.lasso_token_url, data=json.dumps(data), headers=headers)
 
        if res.status_code != 200:
            raise Exception("Cannot retrieve LASSO access token.\n{}\n{}".format(res.status_code, res.content))
 
        access_token_resp = json.loads(res.content.decode())
        self.access_token = access_token_resp["access_token"]
        self.access_token_expiration = datetime.now().timestamp() + access_token_resp["expires_in"]
 
    # Reuse existing LASSO access token until it expires
    def get_access_token(self):
        # If access token expires in a minute, retrieve a new one
        if datetime.now().timestamp() + 60 > self.access_token_expiration:
            self.get_new_access_token()
        return self.access_token
    
lasso_token_client = LassoTokenClient("https://api.lasso.name.net/rest/user/token", Jira_ID, Jira_Passsword,"name")
access_token = lasso_token_client.get_access_token()