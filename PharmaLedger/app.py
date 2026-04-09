from collections import Counter,defaultdict
from flask import Flask,render_template,request,redirect,abort,flash
from flask_login import LoginManager,login_user,login_required,logout_user,current_user
from database import init_db,get_db
from auth import create_user,login_user_auth,User
from ledger import add_event,verify_chain
from qr_utils import generate_qr
from chain_client import chain
from dotenv import load_dotenv
import secrets

load_dotenv()
load_dotenv("chain/.env")

app=Flask(__name__)
app.secret_key="secret123"
login_manager=LoginManager(app)
login_manager.login_view="login"

@login_manager.user_loader
def load_user(uid):
    db=get_db()
    u=db.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
    db.close()
    return User(u["id"],u["name"],u["role"]) if u else None

@app.route("/",methods=["GET","POST"])
def login():
    if request.method=="POST":
        u=login_user_auth(request.form["email"],request.form["password"])
        if u:
            login_user(u)
            return redirect("/dashboard")
    return render_template("login.html")

@app.route("/register",methods=["GET","POST"])
def register():
    if request.method=="POST":
        create_user(request.form["name"],request.form["email"],
                    request.form["password"],request.form["role"])
        return redirect("/")
    return render_template("register.html")

def rows_to_dict(rows):
    return [dict(r) for r in rows]

ROLE_FLOW=["MANUFACTURER","DISTRIBUTOR","HOSPITAL"]
TRANSIT_PREFIX="IN_TRANSIT_TO_"
DISTRIBUTOR_VERIFY_EVENT="DISTRIBUTOR_VERIFIED"

def next_role_for(role):
    if not role:
        return None
    try:
        idx=ROLE_FLOW.index(role)
    except ValueError:
        return None
    return ROLE_FLOW[idx+1] if idx+1<len(ROLE_FLOW) else None

def pending_role_from_status(status):
    if not status or not status.startswith(TRANSIT_PREFIX):
        return None
    return status[len(TRANSIT_PREFIX):]

def possession_status(role):
    if not role:
        return "UNASSIGNED"
    return "DELIVERED" if role==ROLE_FLOW[-1] else f"WITH_{role}"

def enrich_chain(item):
    item["next_role"]=next_role_for(item.get("owner_role"))
    item["pending_role"]=pending_role_from_status(item.get("status"))
    return item

def fetch_drug(drug_uid):
    db=get_db()
    row=db.execute("SELECT * FROM drugs WHERE drug_uid=?",(drug_uid,)).fetchone()
    db.close()
    return dict(row) if row else None

def ledger_has_event(drug_uid,event_name):
    db=get_db()
    row=db.execute("SELECT 1 FROM ledger WHERE drug_uid=? AND event=? LIMIT 1",
        (drug_uid,event_name)).fetchone()
    db.close()
    return bool(row)

def apply_verification_flag(items,verified_set):
    for item in items:
        item["distributor_verified"]=item.get("drug_uid") in verified_set
    return items

@app.route("/dashboard")
@login_required
def dashboard():
    search=request.args.get("q","").strip()
    status_filter=request.args.get("status"," ").strip().upper()

    db=get_db()
    all_drugs=[enrich_chain(d) for d in rows_to_dict(db.execute("SELECT * FROM drugs ORDER BY id DESC").fetchall())]

    clauses=[]
    params=[]
    if search:
        like=f"%{search}%"
        clauses.append("(drug_name LIKE ? OR drug_uid LIKE ? OR batch_no LIKE ?)")
        params.extend([like,like,like])
    if status_filter:
        clauses.append("status=?")
        params.append(status_filter)

    query="SELECT * FROM drugs"
    if clauses:
        query+=" WHERE "+" AND ".join(clauses)
    query+=" ORDER BY id DESC"
    drugs=[enrich_chain(d) for d in rows_to_dict(db.execute(query,params).fetchall())]

    ledger=rows_to_dict(db.execute("SELECT * FROM ledger ORDER BY id DESC").fetchall())
    verified_by_distributor={entry.get("drug_uid") for entry in ledger if entry.get("event")==DISTRIBUTOR_VERIFY_EVENT}
    all_drugs=apply_verification_flag(all_drugs,verified_by_distributor)
    drugs=apply_verification_flag(drugs,verified_by_distributor)
    user_roles=rows_to_dict(db.execute("SELECT role,COUNT(*) as total FROM users GROUP BY role").fetchall())
    db.close()

    def safe_int(value):
        try:
            return int(value)
        except (TypeError,ValueError):
            return 0

    status_counts=Counter((d.get("status") or "UNSET") for d in all_drugs)
    owner_counts=Counter((d.get("owner_role") or "UNASSIGNED") for d in all_drugs)

    qty_by_batch=sorted(
        ({
            "label":f"{d.get('drug_name')} ({d.get('batch_no')})",
            "value":safe_int(d.get("quantity"))
        } for d in all_drugs),
        key=lambda item:item["value"],reverse=True
    )[:6]

    qty_by_owner=defaultdict(int)
    for d in all_drugs:
        owner=d.get("owner_role") or "UNASSIGNED"
        qty_by_owner[owner]+=safe_int(d.get("quantity"))

    event_type_counts=Counter((e.get("event") or "UNSPECIFIED") for e in ledger)
    events_by_day=defaultdict(int)
    for e in ledger:
        ts=str(e.get("timestamp")) if e.get("timestamp") else "Unknown"
        day=ts[:10]
        events_by_day[day]+=1

    role_counts={row.get("role") or "UNSET":row.get("total",0) for row in user_roles}

    chart_data={
        "status":{"labels":list(status_counts.keys()),"values":list(status_counts.values())},
        "owner":{"labels":list(owner_counts.keys()),"values":list(owner_counts.values())},
        "qty":{
            "labels":[item["label"] for item in qty_by_batch],
            "values":[item["value"] for item in qty_by_batch]
        },
        "events":{
            "labels":list(event_type_counts.keys()),
            "values":list(event_type_counts.values())
        },
        "eventsByDay":{
            "labels":sorted(events_by_day.keys()),
            "values":[events_by_day[key] for key in sorted(events_by_day.keys())]
        },
        "roles":{
            "labels":list(role_counts.keys()),
            "values":list(role_counts.values())
        },
        "qtyOwner":{
            "labels":list(qty_by_owner.keys()),
            "values":list(qty_by_owner.values())
        }
    }

    recent_events=ledger[:6]
    status_options=sorted({d.get("status") for d in all_drugs if d.get("status")})

    return render_template(
        "dashboard.html",
        drugs=drugs,
        charts=chart_data,
        recent_events=recent_events,
        filters={"search":search,"status":status_filter},
        status_options=status_options,
        total_drugs=len(all_drugs),
        total_units=sum(safe_int(d.get("quantity")) for d in all_drugs)
    )

@app.route("/create",methods=["GET","POST"])
@login_required
def create():
    if request.method=="POST":
        uid=secrets.token_hex(6)
        qty=int(request.form["qty"])
        db=get_db()
        db.execute("INSERT INTO drugs VALUES(NULL,?,?,?,?,?,?)",
            (uid,request.form["name"],request.form["batch"],
             qty,possession_status("MANUFACTURER"),"MANUFACTURER"))
        db.commit()
        db.close()
        generate_qr(uid)
        try:
            chain.register_drug(uid,request.form["name"],request.form["batch"],qty)
        except Exception:
            pass
        add_event(uid,"CREATED",request.form["location"])
        flash("Data send successfully","success")
        return redirect("/dashboard")
    return render_template("create_drug.html")

@app.route("/transfer/<drug_uid>",methods=["GET","POST"])
@login_required
def transfer(drug_uid):
    drug=fetch_drug(drug_uid)
    if not drug:
        abort(404)
    inspect_url=f"/inspect/{drug_uid}"
    distributor_verified=ledger_has_event(drug_uid,DISTRIBUTOR_VERIFY_EVENT)
    drug["distributor_verified"]=distributor_verified
    in_transit=pending_role_from_status(drug.get("status"))
    if in_transit:
        return render_template("transfer.html",drug=drug,next_role=None,
            error=f"Awaiting receipt by {in_transit.title()} before the next hop.",
            require_verify=False,inspect_url=inspect_url)
    next_holder=next_role_for(drug.get("owner_role"))
    if next_holder is None:
        return render_template("transfer.html",drug=drug,next_role=None,
            error="Chain already complete.",require_verify=False,inspect_url=inspect_url)
    if current_user.role not in (drug.get("owner_role"),"ADMIN"):
        abort(403)
    require_verify=next_holder=="HOSPITAL" and not distributor_verified
    if request.method=="POST":
        location=request.form["location"].strip()
        if not location:
            return render_template("transfer.html",drug=drug,next_role=next_holder,
                error="Location required",require_verify=require_verify,inspect_url=inspect_url)
        db=get_db()
        db.execute("UPDATE drugs SET status=? WHERE drug_uid=?",
            (f"{TRANSIT_PREFIX}{next_holder}",drug_uid))
        db.commit()
        db.close()
        add_event(drug_uid,f"TRANSFER_TO_{next_holder}",location)
        if require_verify:
            flash("Sent to hospital but QC log missing – remember to complete inspection for compliance.","warning")
        else:
            flash("Data send successfully","success")
        return redirect(f"/verify?drug_uid={drug_uid}")
    return render_template("transfer.html",drug=drug,next_role=next_holder,
        error=None,require_verify=require_verify,inspect_url=inspect_url)

@app.route("/receive/<drug_uid>",methods=["GET","POST"])
@login_required
def receive(drug_uid):
    drug=fetch_drug(drug_uid)
    if not drug:
        abort(404)
    expected_role=pending_role_from_status(drug.get("status"))
    if expected_role is None:
        return render_template("receive.html",drug=drug,pending_role=None,error="No inbound shipment for this lot.")
    if current_user.role not in (expected_role,"ADMIN"):
        abort(403)
    if request.method=="POST":
        location=request.form["location"].strip()
        if not location:
            return render_template("receive.html",drug=drug,pending_role=expected_role,error="Location required")
        final_stop=expected_role==ROLE_FLOW[-1]
        new_status="DELIVERED" if final_stop else possession_status(expected_role)
        db=get_db()
        db.execute("UPDATE drugs SET status=?, owner_role=? WHERE drug_uid=?",
            (new_status,expected_role,drug_uid))
        db.commit()
        db.close()
        event_name="DELIVERED" if final_stop else f"RECEIVED_BY_{expected_role}"
        add_event(drug_uid,event_name,location)
        if final_stop:
            flash("Hospital scan recorded. Chain-of-custody complete.","success")
        else:
            flash("Distributor scan captured. Pass the lot to the next hop.","success")
        return redirect(f"/verify?drug_uid={drug_uid}")
    return render_template("receive.html",drug=drug,pending_role=expected_role,error=None)

@app.route("/inspect/<drug_uid>",methods=["GET","POST"])
@login_required
def inspect(drug_uid):
    drug=fetch_drug(drug_uid)
    if not drug:
        abort(404)
    if current_user.role not in ("DISTRIBUTOR","ADMIN"):
        abort(403)
    if current_user.role!="ADMIN" and drug.get("owner_role")!="DISTRIBUTOR":
        abort(403)
    already_verified=ledger_has_event(drug_uid,DISTRIBUTOR_VERIFY_EVENT)
    drug["distributor_verified"]=already_verified
    error=None
    if request.method=="POST":
        if already_verified:
            return redirect(f"/transfer/{drug_uid}")
        notes=request.form.get("notes"," ").strip()
        if not notes:
            error="Inspection notes are required"
        else:
            db=get_db()
            db.execute("UPDATE drugs SET status=? WHERE drug_uid=?",
                ("VERIFIED_BY_DISTRIBUTOR",drug_uid))
            db.commit()
            db.close()
            add_event(drug_uid,DISTRIBUTOR_VERIFY_EVENT,notes)
            flash("Verification data saved successfully","success")
            return redirect(f"/transfer/{drug_uid}")
    return render_template("inspect.html",drug=drug,already_verified=already_verified,error=error)

@app.route("/verify")
@login_required
def verify():
    uid=request.args.get("drug_uid")
    valid=verify_chain(uid) if uid else None
    db=get_db()
    drug=db.execute("SELECT * FROM drugs WHERE drug_uid=?",(uid,)).fetchone()
    events=db.execute("SELECT * FROM ledger WHERE drug_uid=? ORDER BY id",(uid,)).fetchall()
    db.close()
    timeline_message=None
    if events:
        latest_event=(events[-1]["event"] or "").upper()
        if "RECEIVED_BY_DISTRIBUTOR" in latest_event:
            timeline_message="Distributor scan confirmed. Batch is ready for QC or dispatch."
        elif "RECEIVED_BY_HOSPITAL" in latest_event or "DELIVERED" in latest_event:
            timeline_message="Hospital scan recorded. Chain-of-custody is complete."
    
    onchain_events=[]
    chain_error=None
    if uid and chain.enabled:
        try:
            onchain_events=chain.list_events(uid)
        except Exception as exc:
            chain_error=str(exc)
    return render_template("verify.html",drug=drug,events=events,valid=valid,
        onchain_events=onchain_events,chain_enabled=chain.enabled,
        chain_mode=getattr(chain,"mode","disabled"),chain_error=chain_error,
        timeline_message=timeline_message)

@app.route("/audit/<drug_uid>")
@login_required
def audit(drug_uid):
    check=verify_chain(drug_uid)
    db=get_db()
    drug=db.execute("SELECT * FROM drugs WHERE drug_uid=?",(drug_uid,)).fetchone()
    events=db.execute(
        "SELECT * FROM ledger WHERE drug_uid=? ORDER BY id",
        (drug_uid,)
    ).fetchall()
    db.close()
    return render_template("audit.html",drug=drug,events=events,check=check)

@app.route("/scan")
@login_required
def scan():
    return render_template("scan.html")
@app.route("/admin")
@login_required
def admin_dashboard():
    if current_user.role != "ADMIN":
        return redirect("/dashboard")

    db = get_db()
    users = db.execute("SELECT * FROM users").fetchall()
    drugs = db.execute("SELECT * FROM drugs").fetchall()
    ledger = db.execute("SELECT * FROM ledger ORDER BY id DESC").fetchall()
    db.close()

    return render_template(
        "admin_dashboard.html",
        users=users,
        drugs=drugs,
        ledger=ledger
    )

@app.route("/logout")
def logout():
    logout_user()
    return redirect("/")

if __name__=="__main__":
    init_db()
    app.run(debug=True)
