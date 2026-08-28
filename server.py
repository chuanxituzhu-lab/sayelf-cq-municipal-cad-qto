from __future__ import annotations

import base64
import json
import mimetypes
import re
import secrets
import time
import uuid
import os
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from auth import DingTalkAuthError, DingTalkConfig
from cad_qto.job import QtoJobError, run_job
from cad_qto.review import REVIEW_PROTOCOL_VERSION, ReviewInputError, record_job_review, write_job_atomic

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
DATA = ROOT / "data"
EVIDENCE = DATA / "evidence"
CAD_JOBS = DATA / "cad_jobs"
DB_FILE = DATA / "db.json"
CONNECTOR_MANIFEST = ROOT / "connector" / "qwen-project-connector.json"
HOST = "127.0.0.1"
HOST = os.environ.get("MUNICIPAL_LOOP_HOST", HOST).strip() or HOST
PORT = int(os.environ.get("MUNICIPAL_LOOP_PORT", "8765"))
APP_MODE = os.environ.get("MUNICIPAL_LOOP_MODE", "local_demo")
AUTH_CONFIG = DingTalkConfig.from_env()
AUTH_STATES: dict[str, float] = {}
AUTH_SESSIONS: dict[str, dict] = {}
SESSION_TTL_SECONDS = 8 * 60 * 60
TRUSTED_IDENTITY_PROXY = os.environ.get("MUNICIPAL_LOOP_TRUSTED_PROXY", "false").lower() == "true"


ROLE_LINES = {
    "project_manager": "integrated",
    "production_manager": "production",
    "technical_lead": "technical",
    "cost_manager": "cost",
    "construction_survey": "production",
    "material": "production",
    "safety": "production",
    "quality": "technical",
    "laboratory": "technical",
    "document_control": "technical",
    "admin_logistics": "support",
}

ROLE_NAMES = {
    "project_manager": "项目经理",
    "production_manager": "生产经理",
    "technical_lead": "技术负责人",
    "cost_manager": "造价经理",
    "construction_survey": "施工员/测量员",
    "material": "材料员",
    "safety": "安全员",
    "quality": "质量员",
    "laboratory": "实验员",
    "document_control": "资料员",
    "admin_logistics": "行政/后勤",
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


def default_db() -> dict:
    project_id = "DEMO-SZ-2026-001"
    return {
        "project": {
            "project_id": project_id,
            "project_name": "市政工程岗位成果闭环演示项目",
            "contract_no": "DEMO-CONTRACT-001",
            "cost_system_project_no": "COST-DEMO-001",
            "status": "active",
        },
        "members": [
            {"user_id": "demo-project", "user_name": "项目经理（演示）", "role_code": "project_manager", "line": "integrated", "scope": "PROJECT", "active": True, "identity_source": "local_demo", "real_name_verified": False},
            {"user_id": "demo-production", "user_name": "生产经理（演示）", "role_code": "production_manager", "line": "production", "scope": "LINE", "active": True, "identity_source": "local_demo", "real_name_verified": False},
            {"user_id": "demo-technical", "user_name": "技术负责人（演示）", "role_code": "technical_lead", "line": "technical", "scope": "LINE", "active": True, "identity_source": "local_demo", "real_name_verified": False},
            {"user_id": "demo-cost", "user_name": "造价经理（演示）", "role_code": "cost_manager", "line": "cost", "scope": "PROJECT", "active": True, "identity_source": "local_demo", "real_name_verified": False},
        ],
        "tasks": [
            {"task_id": "TASK-001", "project_id": project_id, "period": "本周", "role_code": "construction_survey", "title": "完成 K12-K15 段施工与测量记录", "requirement": "提交完成部位、实际工程量、测量依据和现场照片", "boq_code": "市政-雨水管-001", "due_at": str(date.today())},
            {"task_id": "TASK-002", "project_id": project_id, "period": "本周", "role_code": "material", "title": "完成本周管材进场和领用记录", "requirement": "提交批次、数量、合格证和使用部位", "boq_code": "市政-雨水管-001", "due_at": str(date.today())},
            {"task_id": "TASK-003", "project_id": project_id, "period": "本周", "role_code": "quality", "title": "完成雨水管安装质量检查", "requirement": "提交检查结果、不合格项和整改证据", "boq_code": "市政-雨水管-001", "due_at": str(date.today())},
            {"task_id": "TASK-004", "project_id": project_id, "period": "本周", "role_code": "laboratory", "title": "完成回填压实度取样送检", "requirement": "提交取样部位、日期、报告编号和结果", "boq_code": "市政-回填-001", "due_at": str(date.today())},
            {"task_id": "TASK-005", "project_id": project_id, "period": "本周", "role_code": "production_manager", "title": "完成生产线周计划与偏差说明", "requirement": "比较计划完成量与实际完成量，说明未完成原因", "boq_code": "", "due_at": str(date.today())},
            {"task_id": "TASK-006", "project_id": project_id, "period": "本周", "role_code": "technical_lead", "title": "完成技术质量问题闭环", "requirement": "列明问题、技术措施、责任人和复查结果", "boq_code": "", "due_at": str(date.today())},
            {"task_id": "TASK-007", "project_id": project_id, "period": "本周", "role_code": "cost_manager", "title": "完成本周工程量造价验证", "requirement": "核对生产证、技术证和计价依据", "boq_code": "市政-雨水管-001", "due_at": str(date.today())},
            {"task_id": "TASK-008", "project_id": project_id, "period": "本周", "role_code": "admin_logistics", "title": "完成项目会议与后勤保障记录", "requirement": "提交会议事项、责任人、车辆和后勤保障情况", "boq_code": "", "due_at": str(date.today())},
        ],
        "records": [],
        "reviews": [],
        "cost_facts": [],
        "cad_jobs": [],
        "audit_events": [],
    }


def load_db() -> dict:
    DATA.mkdir(exist_ok=True)
    EVIDENCE.mkdir(exist_ok=True)
    if not DB_FILE.exists():
        db = default_db()
        save_db(db)
        return db
    try:
        db = json.loads(DB_FILE.read_text(encoding="utf-8"))
        db.setdefault("cad_jobs", [])
        db.setdefault("audit_events", [])
        return db
    except (OSError, json.JSONDecodeError):
        return default_db()


def save_db(db: dict) -> None:
    DATA.mkdir(exist_ok=True)
    temporary = DB_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(DB_FILE)


def audit(db: dict, action: str, actor: str, object_id: str, details: str = "") -> None:
    db["audit_events"].append({
        "event_id": new_id("AUD"),
        "action": action,
        "actor": actor,
        "object_id": object_id,
        "details": details,
        "created_at": now_iso(),
    })


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", name or "photo.jpg")
    return cleaned[:80] or "photo.jpg"


class Handler(BaseHTTPRequestHandler):
    server_version = "MunicipalLoop/0.1"

    def log_message(self, fmt: str, *args) -> None:
        print(fmt % args)

    def send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def send_redirect(self, location: str, cookie: str | None = None) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 12 * 1024 * 1024:
            raise ValueError("请求数据过大")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/auth/dingtalk/start":
            self.dingtalk_start()
            return
        if parsed.path == "/auth/dingtalk/callback":
            self.dingtalk_callback(parsed)
            return
        if parsed.path == "/auth/logout":
            self.logout()
            return
        if parsed.path.startswith("/api/"):
            self.api_get(parsed)
            return
        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self.send_json({"error": "不支持的请求"}, HTTPStatus.NOT_FOUND)
            return
        try:
            body = self.read_json()
            self.api_post(parsed.path, body)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # keep prototype errors visible without exposing stack traces
            self.send_json({"error": f"服务处理失败：{exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def serve_static(self, path: str) -> None:
        relative = path.lstrip("/") or "index.html"
        if ".." in Path(relative).parts:
            self.send_json({"error": "非法路径"}, HTTPStatus.BAD_REQUEST)
            return
        target = (WEB / relative).resolve()
        if WEB.resolve() not in target.parents and target != WEB.resolve():
            self.send_json({"error": "非法路径"}, HTTPStatus.BAD_REQUEST)
            return
        if not target.exists() or not target.is_file():
            target = WEB / "index.html"
        content = target.read_bytes()
        mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{mime}; charset=utf-8" if mime.startswith("text/") else mime)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def dingtalk_start(self) -> None:
        if APP_MODE == "local_demo":
            self.send_json({"error": "演示模式不启用钉钉登录"}, HTTPStatus.BAD_REQUEST)
            return
        if not AUTH_CONFIG.configured:
            self.send_json({"error": "钉钉登录尚未配置客户端、企业和 HTTPS 回调参数"}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if not AUTH_CONFIG.redirect_uri.lower().startswith("https://"):
            self.send_json({"error": "正式模式的钉钉回调地址必须使用 HTTPS"}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        now = time.time()
        for state, expires_at in list(AUTH_STATES.items()):
            if expires_at <= now:
                AUTH_STATES.pop(state, None)
        state = secrets.token_urlsafe(32)
        AUTH_STATES[state] = now + 5 * 60
        try:
            location = AUTH_CONFIG.authorization_url(state)
        except DingTalkAuthError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        self.send_redirect(location)

    def dingtalk_callback(self, parsed) -> None:
        if APP_MODE == "local_demo":
            self.send_json({"error": "演示模式不接收钉钉回调"}, HTTPStatus.BAD_REQUEST)
            return
        query = parse_qs(parsed.query)
        state = query.get("state", [""])[0]
        code = query.get("code", [""])[0]
        if query.get("error", [""])[0]:
            self.send_json({"error": "钉钉登录未完成"}, HTTPStatus.UNAUTHORIZED)
            return
        expires_at = AUTH_STATES.pop(state, None)
        if not state or expires_at is None or expires_at <= time.time():
            self.send_json({"error": "钉钉登录状态已失效，请重新发起登录"}, HTTPStatus.BAD_REQUEST)
            return
        if not code:
            self.send_json({"error": "钉钉未返回授权码"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            access_token = AUTH_CONFIG.exchange_code(code)
            identity = AUTH_CONFIG.fetch_userinfo(access_token)
        except DingTalkAuthError:
            self.send_json({"error": "钉钉身份核验失败，请联系项目管理员"}, HTTPStatus.UNAUTHORIZED)
            return
        if identity.get("corp_id") and identity["corp_id"] != AUTH_CONFIG.corp_id:
            self.send_json({"error": "钉钉账号不属于当前项目企业"}, HTTPStatus.FORBIDDEN)
            return

        db = load_db()
        member = next((item for item in db["members"] if item["user_id"] == identity["user_id"]), None)
        if member is None or not member.get("active", False):
            self.send_json({"error": "钉钉账号未加入当前项目人员名单"}, HTTPStatus.FORBIDDEN)
            return
        member["identity_source"] = "dingtalk_enterprise"
        member["user_name"] = identity.get("user_name") or member.get("user_name")
        if identity.get("real_name_verified"):
            member["real_name_verified"] = True
        if not member.get("real_name_verified", False):
            audit(db, "DINGTALK_IDENTITY_REJECTED", identity["user_id"], member["user_id"], "实名认证门禁未通过")
            save_db(db)
            self.send_json({"error": "钉钉账号已识别，但实名认证门禁未通过"}, HTTPStatus.FORBIDDEN)
            return

        member["last_identity_at"] = now_iso()
        session_id = secrets.token_urlsafe(32)
        AUTH_SESSIONS[session_id] = {"user_id": member["user_id"], "expires_at": time.time() + SESSION_TTL_SECONDS}
        audit(db, "DINGTALK_LOGIN", member["user_id"], db["project"]["project_id"], "企业成员与实名认证核验通过")
        save_db(db)
        secure = "; Secure" if AUTH_CONFIG.redirect_uri.lower().startswith("https://") else ""
        cookie = f"municipal_loop_session={session_id}; Max-Age={SESSION_TTL_SECONDS}; Path=/; HttpOnly; SameSite=Lax{secure}"
        self.send_redirect("/", cookie)

    def logout(self) -> None:
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:
            pass
        session = cookie.get("municipal_loop_session")
        if session:
            AUTH_SESSIONS.pop(session.value, None)
        self.send_redirect("/", "municipal_loop_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax")

    def api_get(self, parsed) -> None:
        db = load_db()
        if parsed.path == "/api/bootstrap":
            current_member = self.require_authenticated_member(db)
            if APP_MODE != "local_demo" and current_member is None:
                return
            self.send_json({
                "project": db["project"],
                "roles": ([{"code": current_member["role_code"], "name": ROLE_NAMES[current_member["role_code"]], "line": current_member["line"]}] if current_member else [{"code": code, "name": name, "line": ROLE_LINES[code]} for code, name in ROLE_NAMES.items()]),
                "categories": {"construction_survey": ["施工", "测量"], "admin_logistics": ["行政", "后勤"]},
                "mode": APP_MODE,
                "current_member": current_member,
            })
            return
        if parsed.path == "/api/connector/manifest":
            if not CONNECTOR_MANIFEST.exists():
                self.send_json({"error": "连接器清单不存在"}, HTTPStatus.NOT_FOUND)
                return
            self.send_json(json.loads(CONNECTOR_MANIFEST.read_text(encoding="utf-8")))
            return
        if parsed.path == "/api/connector/user-context":
            query = parse_qs(parsed.query)
            if APP_MODE == "local_demo":
                user_id = query.get("user_id", [""])[0] or self.headers.get("X-DingTalk-User-Id", "")
                member = next((m for m in db["members"] if m["user_id"] == user_id and m.get("active", False)), None)
            else:
                member = self.require_authenticated_member(db)
            if not member:
                if APP_MODE == "local_demo":
                    self.send_json({"error": "当前用户未加入本项目"}, HTTPStatus.FORBIDDEN)
                return
            self.send_json({
                "project": db["project"],
                "member": member,
                "permissions": {"scope": member["scope"], "line": member["line"]},
            })
            return
        if parsed.path == "/api/admin/bootstrap":
            admin = self.require_project_admin(db)
            if APP_MODE != "local_demo" and admin is None:
                return
            self.send_json({"mode": APP_MODE, "project": db["project"], "members": db["members"], "roles": [{"code": code, "name": name, "line": ROLE_LINES[code]} for code, name in ROLE_NAMES.items()]})
            return
        if parsed.path == "/api/state":
            query = parse_qs(parsed.query)
            current_member = self.require_authenticated_member(db)
            if APP_MODE != "local_demo" and current_member is None:
                return
            role = current_member["role_code"] if current_member else query.get("role", [""])[0]
            records = db["records"]
            if role and role not in {"project_manager", "production_manager", "technical_lead", "cost_manager"}:
                records = [r for r in records if r["role_code"] == role]
            summary = {
                "task_count": len(db["tasks"]),
                "record_count": len(db["records"]),
                "pending_review": sum(1 for r in db["records"] if r["status"] in {"待本线审核", "待交叉验证"}),
                "cost_queue": sum(1 for r in db["records"] if r["status"] == "待造价验证"),
                "verified": sum(1 for r in db["records"] if r["status"] in {"验证合格", "已进入造价系统"}),
            }
            self.send_json({"project": db["project"], "tasks": db["tasks"], "records": records, "reviews": db["reviews"], "cost_facts": db["cost_facts"], "summary": summary})
            return
        if parsed.path == "/api/report":
            report = make_report(db)
            self.send_json({"report": report})
            return
        if parsed.path == "/api/cad/status":
            self.cad_status(db)
            return
        if parsed.path == "/api/cad/jobs":
            self.cad_jobs_list(db)
            return
        if parsed.path.startswith("/api/cad/jobs/"):
            self.cad_job_detail(db, parsed.path.rsplit("/", 1)[-1])
            return
        self.send_json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)

    def current_member(self, db: dict):
        if APP_MODE == "local_demo":
            return None
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:
            pass
        session_cookie = cookie.get("municipal_loop_session")
        if session_cookie:
            session_id = session_cookie.value
            session = AUTH_SESSIONS.get(session_id)
            if session and session.get("expires_at", 0) > time.time():
                return next((m for m in db["members"] if m["user_id"] == session["user_id"] and m.get("active", False)), None)
            AUTH_SESSIONS.pop(session_id, None)
        if TRUSTED_IDENTITY_PROXY:
            user_id = self.headers.get("X-DingTalk-User-Id", "").strip()
            if user_id:
                return next((m for m in db["members"] if m["user_id"] == user_id and m.get("active", False)), None)
        return None

    def require_authenticated_member(self, db: dict):
        if APP_MODE == "local_demo":
            return None
        member = self.current_member(db)
        if member is None:
            self.send_json({"error": "未检测到已认证的钉钉企业成员身份"}, HTTPStatus.UNAUTHORIZED)
            return None
        if member.get("identity_source") != "dingtalk_enterprise" or not member.get("real_name_verified", False):
            self.send_json({"error": "钉钉实名认证或企业成员核验未通过"}, HTTPStatus.FORBIDDEN)
            return None
        return member

    def require_project_admin(self, db: dict):
        if APP_MODE == "local_demo":
            return None
        member = self.require_authenticated_member(db)
        if member is None:
            return None
        if member.get("role_code") != "project_manager":
            self.send_json({"error": "只有已认证的项目经理可以维护项目设置和人员归口"}, HTTPStatus.FORBIDDEN)
            return None
        return member

    def api_post(self, path: str, body: dict) -> None:
        db = load_db()
        if path == "/api/records":
            self.create_record(db, body)
            return
        if path == "/api/reviews":
            self.create_review(db, body)
            return
        if path == "/api/cost-validation":
            self.cost_validation(db, body)
            return
        if path == "/api/cad/retaining":
            self.create_cad_job(db, body)
            return
        if path.startswith("/api/cad/jobs/") and path.endswith("/review"):
            parts = path.strip("/").split("/")
            if len(parts) == 5:
                self.review_cad_job(db, parts[3], body)
                return
            self.send_json({"error": "审核接口路径不合法"}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/admin/project":
            self.update_project(db, body)
            return
        if path == "/api/admin/members":
            self.update_member(db, body)
            return
        if path == "/api/reset-demo":
            if APP_MODE != "local_demo":
                self.send_json({"error": "正式模式不允许重置项目数据"}, HTTPStatus.FORBIDDEN)
                return
            save_db(default_db())
            self.send_json({"ok": True})
            return
        self.send_json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)

    def _project_path(self, value: str) -> Path:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(ROOT.resolve())
        except ValueError as exc:
            raise ValueError("图纸路径必须位于当前项目目录内，不能读取项目目录外文件") from exc
        return resolved

    def _job_path_label(self, value: str | Path) -> str:
        path = Path(value).resolve()
        try:
            return str(path.relative_to(ROOT.resolve()))
        except ValueError:
            return "PROJECT_PRIVATE_STORAGE"

    def _require_member_for_cad(self, db: dict):
        current_member = self.current_member(db)
        if APP_MODE != "local_demo" and current_member is None:
            self.send_json({"error": "未检测到已认证的钉钉用户身份"}, HTTPStatus.UNAUTHORIZED)
            return None
        return current_member

    def cad_status(self, db: dict) -> None:
        if self._require_member_for_cad(db) is None and APP_MODE != "local_demo":
            return
        self.send_json({
            "project_id": db["project"]["project_id"],
            "scope": "PROJECT_PRIVATE",
            "input_formats": ["ASCII DXF"],
            "canonical_output": "ASCII DXF（保守实体子集）",
            "supported_entities": ["LINE", "LWPOLYLINE", "TEXT", "MTEXT"],
            "retaining_rule_pack": "cq-municipal-retaining-v0.1",
            "review_protocol_version": REVIEW_PROTOCOL_VERSION,
            "review_states": ["REVIEW_REQUIRED", "REVIEWED_PENDING_AUTHORITY", "FACT_CONFIRMED", "RETURNED", "REJECTED"],
            "recognition_status": "Hypothesis",
            "calculation_status": "Inference",
            "review_required": True,
            "dwg_conversion": "未内置；须采用项目私有环境中经审查的本地转换器",
        })

    def cad_jobs_list(self, db: dict) -> None:
        if self._require_member_for_cad(db) is None and APP_MODE != "local_demo":
            return
        self.send_json({"jobs": db.get("cad_jobs", [])})

    def cad_job_detail(self, db: dict, job_id: str) -> None:
        if self._require_member_for_cad(db) is None and APP_MODE != "local_demo":
            return
        if not re.fullmatch(r"[A-Za-z0-9_-]{4,80}", job_id):
            self.send_json({"error": "算量作业编号不合法"}, HTTPStatus.BAD_REQUEST)
            return
        summary = next((job for job in db.get("cad_jobs", []) if job.get("job_id") == job_id), None)
        result_path = CAD_JOBS / f"{job_id}.json"
        if not summary or not result_path.exists():
            self.send_json({"error": "算量作业不存在"}, HTTPStatus.NOT_FOUND)
            return
        self.send_json(json.loads(result_path.read_text(encoding="utf-8")))

    def create_cad_job(self, db: dict, body: dict) -> None:
        current_member = self.require_authenticated_member(db) if APP_MODE != "local_demo" else None
        if APP_MODE != "local_demo" and current_member is None:
            return
        source_value = str(body.get("source_file", body.get("source_path", ""))).strip()
        source = self._project_path(source_value)
        job_id = new_id("CAD")
        input_payload = {
            "job_id": job_id,
            "project_id": db["project"]["project_id"],
            "source_file": str(source),
            "rule_pack_version": body.get("rule_pack_version", "cq-municipal-retaining-v0.1"),
            "sections": body.get("sections", []),
        }
        CAD_JOBS.mkdir(parents=True, exist_ok=True)
        canonical_path = CAD_JOBS / f"{job_id}.canonical.dxf"
        try:
            result = run_job(input_payload, canonical_path=canonical_path)
        except (OSError, QtoJobError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        result["source"]["source_file"] = self._job_path_label(source)
        result["source"]["canonical_file"] = self._job_path_label(canonical_path)
        result_path = CAD_JOBS / f"{job_id}.json"
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        source_relative = self._job_path_label(source)
        canonical_relative = self._job_path_label(canonical_path)
        summary = {
            "job_id": job_id,
            "project_id": db["project"]["project_id"],
            "source_file": source_relative,
            "canonical_file": canonical_relative,
            "source_sha256": result["source"]["source_sha256"],
            "canonical_sha256": result["source"]["canonical_sha256"],
            "rule_pack_version": result["calculation"]["rule_pack_version"],
            "status": result["status"],
            "review_status": result["calculation"]["review_status"],
            "warning_count": len(result["calculation"]["warnings"]) + len(result["source"]["warnings"]),
            "quantity_count": len(result["calculation"]["quantities"]),
            "created_at": result["created_at"],
        }
        db.setdefault("cad_jobs", []).append(summary)
        actor = current_member["user_id"] if current_member else "local-demo-cad-operator"
        audit(db, "CALCULATE_CAD_QTO", actor, job_id, f"{source_relative};{summary['rule_pack_version']};REVIEW_REQUIRED")
        save_db(db)
        self.send_json({"ok": True, "job": result, "summary": summary}, HTTPStatus.CREATED)

    def review_cad_job(self, db: dict, job_id: str, body: dict) -> None:
        current_member = self.require_authenticated_member(db) if APP_MODE != "local_demo" else None
        if APP_MODE != "local_demo" and current_member is None:
            return
        if not re.fullmatch(r"[A-Za-z0-9_-]{4,80}", job_id):
            self.send_json({"error": "算量作业编号不合法"}, HTTPStatus.BAD_REQUEST)
            return
        summary = next((job for job in db.get("cad_jobs", []) if job.get("job_id") == job_id), None)
        result_path = CAD_JOBS / f"{job_id}.json"
        if not summary or not result_path.exists():
            self.send_json({"error": "算量作业不存在"}, HTTPStatus.NOT_FOUND)
            return
        try:
            job = json.loads(result_path.read_text(encoding="utf-8"))
            verified_reviewer_id = current_member["user_id"] if current_member else None
            review_input = dict(body)
            review_input.setdefault("job_id", job_id)
            reviewed = record_job_review(job, review_input, verified_reviewer_id=verified_reviewer_id)
            write_job_atomic(result_path, reviewed)
        except (OSError, json.JSONDecodeError, ReviewInputError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        summary["status"] = reviewed["status"]
        summary["review_status"] = reviewed["calculation"]["review_status"]
        summary["review_id"] = reviewed["review"]["last_review_id"]
        actor = current_member["user_id"] if current_member else body.get("reviewer_id", "local-demo-reviewer")
        audit(db, "REVIEW_CAD_QTO", actor, job_id, f"{reviewed['status']};{reviewed['calculation']['review_status']}")
        save_db(db)
        self.send_json({"ok": True, "job": reviewed, "summary": summary})

    def update_project(self, db: dict, body: dict) -> None:
        admin = self.require_project_admin(db)
        if APP_MODE != "local_demo" and admin is None:
            return
        project = db["project"]
        for field in ("project_name", "contract_no", "cost_system_project_no"):
            if field in body:
                project[field] = str(body[field]).strip()
        audit(db, "UPDATE_PROJECT_SETTINGS", admin["user_id"] if admin else "local-demo-admin", project["project_id"], "项目基础信息")
        save_db(db)
        self.send_json({"ok": True, "project": project})

    def update_member(self, db: dict, body: dict) -> None:
        admin = self.require_project_admin(db)
        if APP_MODE != "local_demo" and admin is None:
            return
        user_id = str(body.get("user_id", "")).strip()
        user_name = str(body.get("user_name", "")).strip()
        role_code = str(body.get("role_code", "")).strip()
        if not user_id or not user_name or role_code not in ROLE_LINES:
            raise ValueError("人员、岗位和岗位编码不能为空")
        scope = "PROJECT" if role_code in {"project_manager", "cost_manager"} else ("LINE" if role_code in {"production_manager", "technical_lead"} else "SELF")
        member = next((m for m in db["members"] if m["user_id"] == user_id), None)
        if member is None:
            member = {"user_id": user_id}
            db["members"].append(member)
        if APP_MODE == "local_demo":
            identity_source = str(body.get("identity_source", "local_demo"))
            real_name_verified = bool(body.get("real_name_verified", False))
            actor = "local-demo-admin"
        else:
            identity_source = member.get("identity_source", "pending_roster")
            real_name_verified = bool(body.get("real_name_verified", member.get("real_name_verified", False)))
            actor = admin["user_id"]
            if real_name_verified:
                member["verified_at"] = now_iso()
                member["verified_by"] = actor
            else:
                member.pop("verified_at", None)
                member.pop("verified_by", None)
        member.update({"user_name": user_name, "role_code": role_code, "line": ROLE_LINES[role_code], "scope": scope, "active": bool(body.get("active", member.get("active", True))), "identity_source": identity_source, "real_name_verified": real_name_verified})
        audit(db, "UPSERT_PROJECT_MEMBER", actor, user_id, f"{user_name}:{role_code}")
        save_db(db)
        self.send_json({"ok": True, "member": member})

    def create_record(self, db: dict, body: dict) -> None:
        required = ["task_id", "work_category", "work_date", "description"]
        missing = [key for key in required if not str(body.get(key, "")).strip()]
        if missing:
            raise ValueError("缺少必填项：" + "、".join(missing))
        current_member = self.require_authenticated_member(db)
        if APP_MODE != "local_demo" and current_member is None:
            return
        role_code = current_member["role_code"] if current_member else str(body.get("role_code", "")).strip()
        if APP_MODE == "local_demo" and not role_code:
            raise ValueError("演示模式需要选择岗位")
        allowed_categories = {"construction_survey": {"施工", "测量"}, "admin_logistics": {"行政", "后勤"}}
        if role_code in allowed_categories and body["work_category"] not in allowed_categories[role_code]:
            raise ValueError("当前岗位不支持该工作类别")
        task = next((t for t in db["tasks"] if t["task_id"] == body["task_id"]), None)
        if not task:
            raise ValueError("任务不存在")
        if task["role_code"] != role_code:
            raise ValueError("当前岗位不能提交该任务")
        record_id = new_id("REC")
        evidence_items = []
        for evidence in body.get("evidence", [])[:5]:
            encoded = str(evidence.get("data", ""))
            if "," not in encoded:
                continue
            header, content = encoded.split(",", 1)
            if len(content) > 8 * 1024 * 1024:
                raise ValueError("单个照片过大")
            ext = "jpg"
            if "png" in header:
                ext = "png"
            evidence_id = new_id("EVD")
            filename = safe_filename(evidence.get("name", f"{evidence_id}.{ext}"))
            target = EVIDENCE / f"{evidence_id}-{filename}"
            target.write_bytes(base64.b64decode(content))
            evidence_items.append({
                "evidence_id": evidence_id,
                "file_name": filename,
                "file_path": str(target.relative_to(ROOT)),
                "evidence_type": evidence.get("type", "现场照片"),
                "captured_at": body.get("work_date"),
            })
        record = {
            "record_id": record_id,
            "project_id": db["project"]["project_id"],
            "task_id": body["task_id"],
            "period": body.get("period", "本周"),
            "responsible_user_id": current_member["user_id"] if current_member else body.get("responsible_user_id", f"demo-{role_code}"),
            "role_code": role_code,
            "work_category": body["work_category"],
            "work_date": body["work_date"],
            "location": str(body.get("location", "")),
            "description": str(body["description"]).strip(),
            "planned_quantity": body.get("planned_quantity", ""),
            "actual_quantity": body.get("actual_quantity", ""),
            "unit": body.get("unit", ""),
            "boq_code": task.get("boq_code", ""),
            "evidence": evidence_items,
            "status": "待本线审核",
            "created_at": now_iso(),
        }
        db["records"].append(record)
        audit(db, "CREATE_WORK_RECORD", record["responsible_user_id"], record_id, record["description"][:80])
        save_db(db)
        self.send_json({"ok": True, "record": record}, HTTPStatus.CREATED)

    def create_review(self, db: dict, body: dict) -> None:
        record = next((r for r in db["records"] if r["record_id"] == body.get("record_id")), None)
        if not record:
            raise ValueError("成果记录不存在")
        line = body.get("review_line")
        result = body.get("result")
        if line not in {"production", "technical"} or result not in {"通过", "退回补证", "数据冲突"}:
            raise ValueError("审核参数不正确")
        current_member = self.require_authenticated_member(db)
        if APP_MODE != "local_demo":
            if current_member is None:
                return
            if current_member["line"] != line or current_member["role_code"] not in {"production_manager", "technical_lead"}:
                self.send_json({"error": "当前岗位无权执行该归口审核"}, HTTPStatus.FORBIDDEN)
                return
        review = {
            "review_id": new_id("REV"),
            "project_id": db["project"]["project_id"],
            "record_id": record["record_id"],
            "review_line": line,
            "reviewer_user_id": current_member["user_id"] if current_member else body.get("reviewer_user_id", f"demo-{line}"),
            "review_result": result,
            "review_comment": str(body.get("comment", "")),
            "reviewed_at": now_iso(),
        }
        db["reviews"].append(review)
        if result == "退回补证":
            record["status"] = "退回补证"
        elif result == "数据冲突":
            record["status"] = "数据冲突"
        else:
            line_reviews = {r["review_line"]: r for r in db["reviews"] if r["record_id"] == record["record_id"] and r["review_result"] == "通过"}
            record["status"] = "待造价验证" if {"production", "technical"}.issubset(line_reviews) else "待交叉验证"
        audit(db, "LINE_REVIEW", review["reviewer_user_id"], record["record_id"], f"{line}:{result}")
        save_db(db)
        self.send_json({"ok": True, "record": record, "review": review})

    def cost_validation(self, db: dict, body: dict) -> None:
        record = next((r for r in db["records"] if r["record_id"] == body.get("record_id")), None)
        if not record:
            raise ValueError("成果记录不存在")
        if record["status"] != "待造价验证":
            raise ValueError("该记录尚未满足生产和技术交叉验证条件")
        if not record["evidence"]:
            raise ValueError("缺少现场证据，不能进行造价验证")
        current_member = self.require_authenticated_member(db)
        if APP_MODE != "local_demo":
            if current_member is None:
                return
            if current_member["role_code"] != "cost_manager":
                self.send_json({"error": "只有造价经理可以执行造价验证"}, HTTPStatus.FORBIDDEN)
                return
        result = body.get("result")
        if result not in {"合格", "退回补证"}:
            raise ValueError("造价验证结果不正确")
        if result == "退回补证":
            record["status"] = "退回补证"
        else:
            approved_reviews = {
                review["review_line"]: review
                for review in db["reviews"]
                if review["record_id"] == record["record_id"] and review["review_result"] == "通过"
            }
            record["status"] = "验证合格"
            fact = {
                "cost_fact_id": new_id("COST"),
                "project_id": record["project_id"],
                "record_id": record["record_id"],
                "boq_code": record["boq_code"],
                "location": record["location"],
                "verified_quantity": record["actual_quantity"],
                "unit": record["unit"],
                "production_evidence_id": record["evidence"][0]["evidence_id"],
                "technical_evidence_id": approved_reviews.get("technical", {}).get("review_id", ""),
                "cost_evidence_id": body.get("cost_evidence_id", "人工核验"),
                "validation_result": "合格",
                "cost_system_ref": "待接入造价系统",
                "verified_at": now_iso(),
            }
            db["cost_facts"].append(fact)
        audit(db, "COST_VALIDATION", current_member["user_id"] if current_member else body.get("reviewer_user_id", "demo-cost"), record["record_id"], result)
        save_db(db)
        self.send_json({"ok": True, "record": record})


def make_report(db: dict) -> str:
    records = db["records"]
    lines = [
        f"项目：{db['project']['project_name']}",
        f"生成时间：{now_iso()}",
        "",
        f"本期任务：{len(db['tasks'])} 项；已提交成果：{len(records)} 项。",
        f"待本线/交叉审核：{sum(1 for r in records if r['status'] in {'待本线审核', '待交叉验证'})} 项。",
        f"待造价验证：{sum(1 for r in records if r['status'] == '待造价验证')} 项。",
        f"验证合格：{sum(1 for r in records if r['status'] in {'验证合格', '已进入造价系统'})} 项。",
        "",
        "下期计划：由各岗位在任务基线中补充，系统将按责任岗位自动汇总。",
    ]
    if records:
        lines.extend(["", "本期成果摘要："])
        for record in records[-10:]:
            lines.append(f"- {ROLE_NAMES.get(record['role_code'], record['role_code'])}：{record['description'][:80]}（{record['status']}）")
    return "\n".join(lines)


def main() -> None:
    print(f"市政工程岗位成果闭环系统运行中：http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
