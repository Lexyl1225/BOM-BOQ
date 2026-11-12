import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Any
from sqlalchemy.orm import Session
from app.config import settings, BASE_DIR
from app.models import User, Document, DocumentAttachment, ActivityLog, CostEstimate
from app.auth import get_password_hash

logger = logging.getLogger("bom_app")

def parse_dt(val):
    if not val or str(val).strip() in ("", "0000-00-00 00:00:00", "NULL", "None"):
        return None
    s = str(val).strip()
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d")
        except Exception:
            return None

def parse_sql_values(text: str) -> List[List[Any]]:
    """Parse MySQL INSERT VALUES tuple syntax into Python lists."""
    values = []
    i = 0
    n = len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n,":
            i += 1
        if i >= n or text[i] != "(":
            break
        i += 1  # skip '('
        row = []
        while i < n:
            while i < n and text[i] in " \t\r\n":
                i += 1
            if i >= n:
                break
            if text[i] == ")":
                i += 1
                break
            if text[i] == ",":
                i += 1
                continue
            if text[i] == "'":  # single quote
                i += 1
                val = []
                while i < n:
                    if text[i] == "\\":
                        if i + 1 < n:
                            c = text[i + 1]
                            if c == "n": val.append("\n")
                            elif c == "r": val.append("\r")
                            elif c == "t": val.append("\t")
                            elif c == "0": val.append("\0")
                            elif c == "'": val.append("'")
                            elif c == '"': val.append('"')
                            elif c == "\\": val.append("\\")
                            else: val.append(c)
                            i += 2
                        else:
                            i += 1
                    elif text[i] == "'":
                        if i + 1 < n and text[i + 1] == "'":
                            val.append("'")
                            i += 2
                        else:
                            i += 1
                            break
                    else:
                        val.append(text[i])
                        i += 1
                row.append("".join(val))
            else:
                # number or NULL
                val = []
                while i < n and text[i] not in ",) \t\r\n":
                    val.append(text[i])
                    i += 1
                token = "".join(val)
                if token.upper() == "NULL":
                    row.append(None)
                elif token.isdigit():
                    row.append(int(token))
                else:
                    try:
                        row.append(float(token))
                    except ValueError:
                        row.append(token)
        values.append(row)
    return values

def seed_database(db: Session):
    """Seed SQLite database with existing dump data and users if empty."""
    user_count = db.query(User).count()
    if user_count > 0:
        logger.info(f"Database already contains {user_count} users. Skipping full initial seed.")
        return

    logger.info("Empty database detected. Starting automated migration from SQL dump & JSON files...")
    
    dump_path = BASE_DIR / "bom_db_dump.sql"
    if not dump_path.exists() and (settings.DATA_DIR / "bom_db_dump.sql").exists():
        dump_path = settings.DATA_DIR / "bom_db_dump.sql"
    dump_text = ""
    if dump_path.exists():
        with open(dump_path, "r", encoding="utf-8", errors="ignore") as f:
            dump_text = f.read()

    # 1. Seed Users
    seeded_user_ids = set()
    if dump_text and "INSERT INTO `users` VALUES" in dump_text:
        u_idx = dump_text.find("INSERT INTO `users` VALUES")
        u_end = dump_text.find(";", u_idx)
        u_sql = dump_text[u_idx + len("INSERT INTO `users` VALUES"):u_end].strip()
        parsed_users = parse_sql_values(u_sql)
        for u in parsed_users:
            try:
                # schema: id, username, password, role, department, email, created_at, updated_at, last_login, is_active
                uid = int(u[0])
                uname = str(u[1])
                upass = str(u[2])
                urole = str(u[3]) if u[3] else "guest"
                udept = str(u[4]) if u[4] else ""
                uemail = str(u[5]) if u[5] else None
                ucreated = parse_dt(u[6]) or datetime.utcnow()
                uupdated = parse_dt(u[7]) or datetime.utcnow()
                ulast = parse_dt(u[8])
                uis_active = bool(u[9]) if len(u) > 9 and u[9] is not None else True
                
                db_user = User(
                    id=uid,
                    username=uname,
                    password=upass,
                    role=urole,
                    department=udept,
                    email=uemail,
                    created_at=ucreated,
                    updated_at=uupdated,
                    last_login=ulast,
                    is_active=uis_active
                )
                db.add(db_user)
                seeded_user_ids.add(uid)
            except Exception as ex:
                logger.warning(f"Error parsing user {u}: {ex}")
        db.commit()
        logger.info(f"Imported {len(seeded_user_ids)} users from SQL dump.")

    # Fallback to users.json if needed
    users_json_path = BASE_DIR / "users.json"
    if not users_json_path.exists() and (settings.DATA_DIR / "users.json").exists():
        users_json_path = settings.DATA_DIR / "users.json"
    if users_json_path.exists():
        with open(users_json_path, "r", encoding="utf-8") as f:
            j_users = json.load(f)
            for ju in j_users:
                existing = db.query(User).filter(User.username == ju["username"]).first()
                if not existing:
                    new_u = User(
                        username=ju["username"],
                        password=ju["password"],
                        role=ju.get("role", "guest"),
                        department=ju.get("department", ""),
                        email=ju.get("email"),
                        created_at=parse_dt(ju.get("created_at")) or datetime.utcnow()
                    )
                    db.add(new_u)
            db.commit()

    # Ensure Admin exists
    admin_user = db.query(User).filter(User.username == "Admin").first()
    if not admin_user:
        admin_user = User(
            username="Admin",
            password=get_password_hash("admin123"),
            role="admin",
            department="Admin",
            created_at=datetime.utcnow()
        )
        db.add(admin_user)
        db.commit()

    # 2. Seed Documents
    if dump_text and "INSERT INTO `documents` VALUES" in dump_text:
        d_idx = dump_text.find("INSERT INTO `documents` VALUES")
        d_end = dump_text.find(";\n/*!40000", d_idx)
        d_sql = dump_text[d_idx + len("INSERT INTO `documents` VALUES"):d_end].strip()
        parsed_docs = parse_sql_values(d_sql)
        for d in parsed_docs:
            try:
                # Schema: id, name, ref_no, type, status, department, project_name, location, date_value, html_content, items, original_type, original_index, created_by, approved_by, approved_at, created_at, updated_at, posted_date, completed_date, unposted_date, last_edited
                doc_id = int(d[0])
                name = str(d[1])
                ref_no = str(d[2])
                dtype = str(d[3]).lower()
                status = str(d[4])
                dept = str(d[5]) if d[5] else None
                pname = str(d[6]) if d[6] else None
                loc = str(d[7]) if d[7] else None
                dval = str(d[8]) if d[8] else None
                html = str(d[9]) if d[9] else ""
                items = str(d[10]) if len(d) > 10 and d[10] else None
                orig_type = str(d[11]) if len(d) > 11 and d[11] else None
                orig_idx = int(d[12]) if len(d) > 12 and d[12] is not None else None
                created_by = int(d[13]) if len(d) > 13 and d[13] else admin_user.id
                approved_by = int(d[14]) if len(d) > 14 and d[14] else None
                approved_at = parse_dt(d[15]) if len(d) > 15 else None
                created_at = parse_dt(d[16]) if len(d) > 16 else datetime.utcnow()
                updated_at = parse_dt(d[17]) if len(d) > 17 else datetime.utcnow()
                posted_date = parse_dt(d[18]) if len(d) > 18 else None
                completed_date = parse_dt(d[19]) if len(d) > 19 else None
                unposted_date = parse_dt(d[20]) if len(d) > 20 else None
                last_edited = parse_dt(d[21]) if len(d) > 21 else None

                doc = Document(
                    id=doc_id,
                    name=name,
                    ref_no=ref_no,
                    type=dtype,
                    status=status,
                    department=dept,
                    project_name=pname,
                    location=loc,
                    date_value=dval,
                    html_content=html,
                    items=items,
                    original_type=orig_type,
                    original_index=orig_idx,
                    created_by=created_by,
                    approved_by=approved_by,
                    approved_at=approved_at,
                    created_at=created_at or datetime.utcnow(),
                    updated_at=updated_at or datetime.utcnow(),
                    posted_date=posted_date,
                    completed_date=completed_date,
                    unposted_date=unposted_date,
                    last_edited=last_edited
                )
                db.add(doc)
            except Exception as ex:
                logger.warning(f"Error parsing document {d[:3] if len(d)>=3 else d}: {ex}")
        db.commit()
        logger.info(f"Imported {len(parsed_docs)} documents from SQL dump.")

    # 3. Seed Attachments
    if dump_text and "INSERT INTO `document_attachments` VALUES" in dump_text:
        a_idx = dump_text.find("INSERT INTO `document_attachments` VALUES")
        a_end = dump_text.find(";", a_idx)
        a_sql = dump_text[a_idx + len("INSERT INTO `document_attachments` VALUES"):a_end].strip()
        parsed_atts = parse_sql_values(a_sql)
        for a in parsed_atts:
            try:
                # Schema: id, document_id, file_name, original_name, file_type, file_size, file_path, uploaded_by, uploaded_at
                att = DocumentAttachment(
                    id=int(a[0]),
                    document_id=int(a[1]),
                    file_name=str(a[2]),
                    original_name=str(a[3]),
                    file_type=str(a[4]),
                    file_size=int(a[5]),
                    file_path=str(a[6]),
                    uploaded_by=int(a[7]),
                    uploaded_at=parse_dt(a[8]) or datetime.utcnow()
                )
                db.add(att)
            except Exception as ex:
                logger.warning(f"Error parsing attachment {a}: {ex}")
        db.commit()
        logger.info(f"Imported {len(parsed_atts)} attachments from SQL dump.")

    # 4. Seed Activity Logs
    if dump_text and "INSERT INTO `activity_logs` VALUES" in dump_text:
        l_idx = dump_text.find("INSERT INTO `activity_logs` VALUES")
        l_end = dump_text.find(";\n/*!40000", l_idx)
        l_sql = dump_text[l_idx + len("INSERT INTO `activity_logs` VALUES"):l_end].strip()
        parsed_logs = parse_sql_values(l_sql)
        for l in parsed_logs:
            try:
                # Schema: id, log_id, timestamp, username, user_id, role, department, action, details, page, ip_address, user_agent
                log_entry = ActivityLog(
                    id=int(l[0]),
                    log_id=str(l[1]),
                    timestamp=parse_dt(l[2]) or datetime.utcnow(),
                    username=str(l[3]),
                    user_id=int(l[4]) if l[4] else None,
                    role=str(l[5]) if l[5] else None,
                    department=str(l[6]) if l[6] else None,
                    action=str(l[7]),
                    details=str(l[8]) if l[8] else None,
                    page=str(l[9]) if l[9] else None,
                    ip_address=str(l[10]) if l[10] else None,
                    user_agent=str(l[11]) if l[11] else None
                )
                db.add(log_entry)
            except Exception as ex:
                logger.warning(f"Error parsing activity log {l[:3] if len(l)>=3 else l}: {ex}")
        db.commit()
        logger.info(f"Imported {len(parsed_logs)} activity logs from SQL dump.")

    # 5. Seed Sample Cost Estimate if none exist
    if db.query(CostEstimate).count() == 0:
        sample_est = CostEstimate(
            estimate_name="SM Mega Center Cabanatuan - Electrical Fitout",
            department="Design and Construction Department",
            materials_total=64500.00,
            labor_total=24000.00,
            meal_allowance=4500.00,
            transportation_allowance=3500.00,
            mobilization_demobilization=5000.00,
            custom_items=json.dumps([
                {"description": "Safety Equipment & PPE gear", "amount": 2500.00},
                {"description": "Permit and Inspection documentation fees", "amount": 3000.00}
            ]),
            source_documents=json.dumps(["BOM FOR SM MEGACENTER CABANATUAN 2ND FLOOR"]),
            grand_total=107000.00,
            created_by=admin_user.id,
            created_at=datetime.utcnow()
        )
        db.add(sample_est)
        db.commit()
        logger.info("Added initial sample project cost estimate.")

    logger.info("Automated migration and database initialization completed successfully!")
