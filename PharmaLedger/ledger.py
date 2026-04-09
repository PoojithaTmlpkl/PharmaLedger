import datetime
import hashlib
import json
import logging

from database import get_db
from chain_client import chain

LOGGER = logging.getLogger("pharmaledger.ledger")

def hash_data(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()

def add_event(drug_uid,event,location):
    db = get_db()
    prev = db.execute("SELECT curr_hash FROM ledger WHERE drug_uid=? ORDER BY id DESC LIMIT 1",(drug_uid,)).fetchone()
    prev_hash = prev["curr_hash"] if prev else "GENESIS"

    payload = {
        "drug_uid":drug_uid,
        "event":event,
        "location":location,
        "prev_hash":prev_hash
    }

    curr_hash = hash_data(payload)

    db.execute("""INSERT INTO ledger VALUES(NULL,?,?,?,?,?,?)""",
        (drug_uid,event,location,prev_hash,curr_hash,datetime.datetime.utcnow().isoformat()))
    db.commit()
    db.close()

    try:
        chain.append_event(drug_uid,event,location,prev_hash,curr_hash)
    except Exception as exc:  # pragma: no cover - network dependent
        LOGGER.warning("Chain append failed for %s: %s", drug_uid, exc)

def verify_chain(drug_uid):
    db = get_db()
    rows = db.execute("SELECT * FROM ledger WHERE drug_uid=? ORDER BY id",(drug_uid,)).fetchall()
    db.close()

    prev="GENESIS"
    for r in rows:
        payload={
            "drug_uid":r["drug_uid"],
            "event":r["event"],
            "location":r["location"],
            "prev_hash":prev
        }
        if hash_data(payload)!=r["curr_hash"]:
            return False
        prev=r["curr_hash"]
    return True
