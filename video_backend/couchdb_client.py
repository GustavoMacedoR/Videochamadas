from pathlib import Path
import os
from dotenv import load_dotenv
import requests

BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / '.env'
if env_path.exists():
    load_dotenv(env_path)

COUCH_USER = os.getenv('COUCHDB_USERNAME')
COUCH_PASS = os.getenv('COUCHDB_PASSWORD')
COUCH_HOST = os.getenv('COUCHDB_HOST')
DEFAULT_DB = os.getenv('COUCHDB_DB', 'videochamadas')

if not all([COUCH_USER, COUCH_PASS, COUCH_HOST]):
    raise RuntimeError('Missing CouchDB configuration in .env')

BASE_URL = f"http://{COUCH_HOST}"
AUTH = (COUCH_USER, COUCH_PASS)


def db_info(dbname: str = None):
    """Return database info for `dbname`."""
    db = dbname or DEFAULT_DB
    resp = requests.get(f"{BASE_URL}/{db}", auth=AUTH)
    resp.raise_for_status()
    return resp.json()


def create_db(dbname: str = None):
    """Create a database if it does not exist. Returns response json or raises."""
    db = dbname or DEFAULT_DB
    resp = requests.put(f"{BASE_URL}/{db}", auth=AUTH)
    if resp.status_code not in (201, 202, 412):
        resp.raise_for_status()
    return resp.status_code


def create_doc(doc: dict, dbname: str = None):
    """Create a document in `dbname`. Returns the response JSON."""
    db = dbname or DEFAULT_DB
    resp = requests.post(f"{BASE_URL}/{db}", json=doc, auth=AUTH)
    resp.raise_for_status()
    return resp.json()


def get_doc(doc_id: str, dbname: str = None):
    db = dbname or DEFAULT_DB
    resp = requests.get(f"{BASE_URL}/{db}/{doc_id}", auth=AUTH)
    resp.raise_for_status()
    return resp.json()


def list_docs(dbname: str = None, include_docs: bool = True, limit: int = 100):
    """List documents in `dbname`. Returns list of rows (can include docs)."""
    db = dbname or DEFAULT_DB
    params = {"include_docs": "true"} if include_docs else {}
    if limit:
        params['limit'] = str(limit)
    resp = requests.get(f"{BASE_URL}/{db}/_all_docs", params=params, auth=AUTH)
    resp.raise_for_status()
    return resp.json()


def update_doc(doc_id: str, doc: dict, dbname: str = None):
    """Update a document by id. `doc` must include `_rev` or function will fetch rev first."""
    db = dbname or DEFAULT_DB
    # If rev not provided, fetch current rev
    if '_rev' not in doc:
        cur = requests.get(f"{BASE_URL}/{db}/{doc_id}", auth=AUTH)
        cur.raise_for_status()
        doc['_rev'] = cur.json().get('_rev')
    resp = requests.put(f"{BASE_URL}/{db}/{doc_id}", json=doc, auth=AUTH)
    resp.raise_for_status()
    return resp.json()


def delete_doc(doc_id: str, dbname: str = None):
    db = dbname or DEFAULT_DB
    # need current rev to delete
    cur = requests.get(f"{BASE_URL}/{db}/{doc_id}", auth=AUTH)
    cur.raise_for_status()
    rev = cur.json().get('_rev')
    resp = requests.delete(f"{BASE_URL}/{db}/{doc_id}", params={'rev': rev}, auth=AUTH)
    resp.raise_for_status()
    return resp.json()
