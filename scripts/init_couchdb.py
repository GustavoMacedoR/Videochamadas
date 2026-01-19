import os
from pathlib import Path
from dotenv import load_dotenv
import requests

BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / '.env'
if env_path.exists():
    load_dotenv(env_path)

COUCH_USER = os.getenv('COUCHDB_USERNAME')
COUCH_PASS = os.getenv('COUCHDB_PASSWORD')
COUCH_HOST = os.getenv('COUCHDB_HOST')
COUCH_DB = os.getenv('COUCHDB_DB', 'videochamadas')

if not all([COUCH_USER, COUCH_PASS, COUCH_HOST]):
    print('Missing CouchDB settings in .env')
    raise SystemExit(1)

base_url = f"http://{COUCH_USER}:{COUCH_PASS}@{COUCH_HOST}"
create_db_url = f"{base_url}/{COUCH_DB}"

print('Attempting to create CouchDB database:', create_db_url)
resp = requests.put(create_db_url)
if resp.status_code in (201, 202):
    print('Database created')
elif resp.status_code == 412:
    print('Database already exists')
else:
    print('Unexpected response:', resp.status_code, resp.text)
    resp.raise_for_status()

# create an example document
docs_url = f"{base_url}/{COUCH_DB}"
example = {"type": "meta", "created_by": "init_couchdb.py"}
resp = requests.post(docs_url, json=example)
if resp.status_code in (201, 202):
    print('Created example document:', resp.json().get('id'))
else:
    print('Failed to create example document:', resp.status_code, resp.text)

print('Done')
