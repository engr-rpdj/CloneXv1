#Note: Remove the comment here if you want to use OpenAi API:
# # backend/main.py

# import io
# import os
# import json
# import shutil
# import logging
# import zipfile
# from pathlib import Path
# from fastapi import FastAPI, UploadFile, File, Form, HTTPException
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import StreamingResponse
# from pydantic import BaseModel
# from typing import List

# from .ingest import load_file, SUPPORTED_EXTENSIONS
# from .retriever import (
#     add_document, search, list_avatars, reset_avatar,
#     save_uploaded_file, load_all_avatars_from_disk,
#     DATA_ROOT, _avatar_dir,
# )
# from .llm import generate_answer

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# app = FastAPI(title="AI Digital Twin API", version="3.0")

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


# # ── Startup: reload all saved avatars from disk ───────────────────────────────

# @app.on_event("startup")
# def startup_event():
#     load_all_avatars_from_disk()
#     logger.info(f"Loaded avatars from disk: {[a['id'] for a in list_avatars()]}")


# # ── Models ────────────────────────────────────────────────────────────────────

# class QuestionRequest(BaseModel):
#     question: str
#     avatar_id: str
#     n_results: int = 3


# class AnswerResponse(BaseModel):
#     answer: str
#     context: List[str]
#     avatar_id: str


# class UploadResponse(BaseModel):
#     avatar_id: str
#     avatar_name: str
#     files_processed: List[str]
#     files_failed: List[dict]
#     total_chunks: int
#     message: str


# class AvatarListResponse(BaseModel):
#     avatars: List[dict]


# # ── Endpoints ─────────────────────────────────────────────────────────────────

# @app.post("/avatar/upload", response_model=UploadResponse)
# async def upload_avatar_documents(
#     name: str = Form(...),
#     avatar_id: str = Form(...),
#     persona: str = Form(""),
#     reset: bool = Form(False),
#     files: List[UploadFile] = File(...),
# ):
#     if not files:
#         raise HTTPException(status_code=400, detail="No files uploaded.")

#     if reset:
#         reset_avatar(avatar_id)
#         logger.info(f"Avatar '{avatar_id}' reset.")

#     files_processed, files_failed, total_chunks = [], [], 0

#     for upload in files:
#         filename = upload.filename or "unknown"
#         try:
#             file_bytes = await upload.read()
#             text = load_file(filename, file_bytes)

#             if not text.strip():
#                 files_failed.append({"file": filename, "reason": "Empty or unreadable file."})
#                 continue

#             save_uploaded_file(file_bytes, filename, avatar_id)

#             chunks_added = add_document(text, source=filename, avatar_id=avatar_id, name=name, persona=persona)
#             total_chunks += chunks_added
#             files_processed.append(filename)
#             logger.info(f"Indexed '{filename}' → {chunks_added} chunks for '{avatar_id}'")

#         except ValueError as e:
#             files_failed.append({"file": filename, "reason": str(e)})
#         except Exception as e:
#             logger.error(f"Failed '{filename}': {e}")
#             files_failed.append({"file": filename, "reason": str(e)})

#     if not files_processed:
#         raise HTTPException(status_code=422, detail={
#             "message": "No files could be processed.",
#             "failures": files_failed,
#             "supported_types": list(SUPPORTED_EXTENSIONS),
#         })

#     return UploadResponse(
#         avatar_id=avatar_id,
#         avatar_name=name,
#         files_processed=files_processed,
#         files_failed=files_failed,
#         total_chunks=total_chunks,
#         message=f"Avatar '{name}' ready — {total_chunks} chunks from {len(files_processed)} file(s). Saved to disk.",
#     )


# @app.post("/avatar/ask", response_model=AnswerResponse)
# def ask_avatar(request: QuestionRequest):
#     from .retriever import get_or_create_avatar
#     store = get_or_create_avatar(request.avatar_id)

#     context_chunks = search(request.question, n_results=request.n_results, avatar_id=request.avatar_id)

#     if not context_chunks:
#         raise HTTPException(status_code=404,
#             detail=f"No data found for avatar '{request.avatar_id}'. Upload documents first.")

#     context = "\n\n".join(context_chunks)
#     answer  = generate_answer(
#         context,
#         request.question,
#         name=store.name,
#         persona=store.persona,
#     )

#     return AnswerResponse(answer=answer, context=context_chunks, avatar_id=request.avatar_id)


# @app.get("/avatars", response_model=AvatarListResponse)
# def get_avatars():
#     return AvatarListResponse(avatars=list_avatars())


# def _render_existing_files(files: list, avatar_id: str) -> str:
#     """Render existing indexed files as HTML rows for the downloaded frontend."""
#     if not files:
#         return '<div style="font-size:12px;color:#a09d96;">No documents indexed yet.</div>'
#     rows = []
#     for f in files:
#         ext = f.rsplit(".", 1)[-1].lower() if "." in f else "other"
#         ext_cls = ext if ext in ["pdf", "txt", "docx", "md"] else "other"
#         rows.append(
#             f'<div class="existing-row">'
#             f'<span class="ext-badge ext-{ext_cls}">{ext}</span>'
#             f'<span style="font-size:13px;flex:1;">{f}</span>'
#             f'<button class="del-btn" onclick="deleteAvatar()">Delete avatar</button>'
#             f'</div>'
#         )
#     return "".join(rows)


# @app.get("/avatar/{avatar_id}/download")
# def download_avatar(avatar_id: str):
#     """
#     Download a complete, ready-to-run GitHub repository zip
#     with a frontend personalized to this specific avatar.
#     """
#     avatar_dir = _avatar_dir(avatar_id)
#     if not avatar_dir.exists():
#         raise HTTPException(status_code=404, detail=f"Avatar '{avatar_id}' not found.")

#     project_root = Path(__file__).parent.parent
#     backend_dir  = Path(__file__).parent
#     repo_name    = avatar_id

#     # Load avatar info
#     from .retriever import get_or_create_avatar
#     store          = get_or_create_avatar(avatar_id)
#     avatar_name    = store.name
#     avatar_persona = store.persona or ""
#     avatar_files   = list(set(store.sources))
#     avatar_initials = "".join([w[0] for w in avatar_name.split()][:2]).upper()

#     # Derive a short role label for the subtitle — strip "You are X" phrasing
#     role_label = "AI Digital Twin"
#     if avatar_persona:
#         # Try to extract a clean role from common persona patterns
#         import re
#         # Match "You are [a/an] <role>" → extract just the role part
#         m = re.search(r"you are (?:a |an |the )?(.+?)(?:\.|,|for\b)", avatar_persona, re.IGNORECASE)
#         if m:
#             candidate = m.group(1).strip()
#             # Clean it up — capitalise first letter, max 50 chars
#             if len(candidate) <= 50:
#                 role_label = candidate[0].upper() + candidate[1:]
#         # Fallback: if no pattern matched, keep default

#     # Welcome message — just a natural greeting, never reads back the persona
#     if avatar_persona:
#         welcome = f"Hi! How can I help you today?"
#     else:
#         welcome = f"Hi! Ask me anything about my background and experience."

#     # Derive a unique accent color from avatar name
#     hue = sum(ord(c) for c in avatar_name) % 360
#     accent           = f"hsl({hue}, 55%, 38%)"
#     accent_bg        = f"hsl({hue}, 55%, 95%)"
#     accent_text      = f"hsl({hue}, 55%, 25%)"
#     accent_hover     = f"hsl({hue}, 55%, 32%)"
#     avatar_bg_color  = f"hsl({hue}, 40%, 90%)"
#     avatar_txt_color = f"hsl({hue}, 40%, 28%)"

#     # Chat placeholder based on persona
#     if "support" in avatar_persona.lower() or "customer" in avatar_persona.lower():
#         placeholder = f"Ask {avatar_name} a question..."
#     elif "sales" in avatar_persona.lower():
#         placeholder = "What would you like to know?"
#     else:
#         placeholder = "Ask me anything..."

#     personalized_frontend = f"""<!DOCTYPE html>
# <html lang="en">
# <head>
# <meta charset="UTF-8" />
# <meta name="viewport" content="width=device-width, initial-scale=1.0" />
# <title>{avatar_name}</title>
# <style>
# *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
# :root {{
#   --bg: #f7f6f3; --surface: #ffffff; --border: #e2e0d8;
#   --border-strong: #c8c6bc; --text: #1c1a16; --text-muted: #6b6963;
#   --text-hint: #a09d96;
#   --accent: {accent}; --accent-bg: {accent_bg}; --accent-text: {accent_text};
#   --accent-hover: {accent_hover};
#   --av-bg: {avatar_bg_color}; --av-text: {avatar_txt_color};
#   --success-bg: #eaf3de; --success-text: #27500a;
#   --error-bg: #fcebeb; --error-text: #791f1f;
#   --radius: 10px; --radius-sm: 6px;
#   --font: 'Segoe UI', system-ui, -apple-system, sans-serif;
# }}
# body {{ font-family: var(--font); background: var(--bg); color: var(--text); height: 100vh; display: flex; flex-direction: column; overflow: hidden; }}

# /* header */
# header {{ display: flex; align-items: center; gap: 12px; padding: 0 1.5rem; height: 52px; background: var(--surface); border-bottom: 1px solid var(--border); flex-shrink: 0; }}
# .av-dot {{ width: 32px; height: 32px; border-radius: 50%; background: var(--av-bg); color: var(--av-text); font-size: 12px; font-weight: 600; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }}
# .av-name {{ font-size: 15px; font-weight: 600; color: var(--text); }}
# .av-role {{ font-size: 12px; color: var(--text-hint); }}
# .online {{ width: 8px; height: 8px; border-radius: 50%; background: #4caf50; margin-left: auto; }}

# /* tabs */
# .tabs {{ display: flex; gap: 0; border-bottom: 1px solid var(--border); background: var(--surface); flex-shrink: 0; padding: 0 1.5rem; }}
# .tab {{ padding: 10px 18px; font-size: 13px; font-weight: 500; color: var(--text-muted); cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.15s; user-select: none; }}
# .tab:hover {{ color: var(--text); }}
# .tab.active {{ color: var(--accent); border-bottom-color: var(--accent); }}

# /* panels */
# .panel {{ display: none; flex: 1; overflow: hidden; flex-direction: column; }}
# .panel.active {{ display: flex; }}

# /* chat */
# .messages {{ flex: 1; overflow-y: auto; padding: 1.5rem; display: flex; flex-direction: column; gap: 1rem; }}
# .msg {{ display: flex; gap: 10px; max-width: 78%; }}
# .msg.user {{ align-self: flex-end; flex-direction: row-reverse; }}
# .msg.bot  {{ align-self: flex-start; }}
# .msg-av {{ width: 30px; height: 30px; border-radius: 50%; font-size: 11px; font-weight: 600; display: flex; align-items: center; justify-content: center; flex-shrink: 0; margin-top: 2px; }}
# .msg.bot  .msg-av {{ background: var(--av-bg); color: var(--av-text); }}
# .msg.user .msg-av {{ background: var(--accent-bg); color: var(--accent-text); }}
# .msg-bubble {{ padding: 9px 13px; border-radius: var(--radius); font-size: 13px; line-height: 1.6; }}
# .msg.bot  .msg-bubble {{ background: var(--surface); border: 1px solid var(--border); color: var(--text); border-top-left-radius: 3px; }}
# .msg.user .msg-bubble {{ background: var(--accent); color: #fff; border-top-right-radius: 3px; }}
# .msg-bubble.typing {{ color: var(--text-hint); font-style: italic; }}
# .chat-input-row {{ padding: 1rem 1.5rem; background: var(--surface); border-top: 1px solid var(--border); display: flex; gap: 10px; align-items: flex-end; flex-shrink: 0; }}
# #chat-input {{ flex: 1; padding: 9px 12px; font-size: 13px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--bg); color: var(--text); outline: none; resize: none; max-height: 120px; line-height: 1.5; font-family: var(--font); transition: border-color 0.15s; }}
# #chat-input:focus {{ border-color: var(--accent); background: var(--surface); }}
# .send-btn {{ padding: 9px 18px; background: var(--accent); color: #fff; border: none; border-radius: var(--radius-sm); font-size: 13px; font-weight: 500; cursor: pointer; transition: background 0.15s; flex-shrink: 0; }}
# .send-btn:hover:not(:disabled) {{ background: var(--accent-hover); }}
# .send-btn:disabled {{ opacity: 0.35; cursor: not-allowed; }}
# .chat-hint {{ font-size: 11px; color: var(--text-hint); text-align: center; padding: 0 0 0.5rem; }}

# /* settings / files shared */
# .settings-body {{ flex: 1; overflow-y: auto; padding: 2rem; max-width: 600px; width: 100%; margin: 0 auto; display: flex; flex-direction: column; gap: 1.5rem; }}
# .field-label {{ font-size: 12px; color: var(--text-muted); margin-bottom: 6px; display: block; font-weight: 500; }}
# textarea.persona-box {{ width: 100%; padding: 10px 12px; font-size: 13px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--bg); color: var(--text); outline: none; resize: vertical; min-height: 160px; font-family: var(--font); line-height: 1.6; transition: border-color 0.15s; }}
# textarea.persona-box:focus {{ border-color: var(--accent); background: var(--surface); }}
# .btn-save {{ padding: 9px 20px; background: var(--accent); color: #fff; border: none; border-radius: var(--radius-sm); font-size: 13px; font-weight: 500; cursor: pointer; transition: background 0.15s; }}
# .btn-save:hover {{ background: var(--accent-hover); }}
# .status-msg {{ font-size: 12px; padding: 8px 12px; border-radius: var(--radius-sm); display: none; }}
# .status-ok  {{ background: var(--success-bg); color: var(--success-text); display: block; }}
# .status-err {{ background: var(--error-bg);   color: var(--error-text);   display: block; }}

# /* files panel */
# .drop-zone {{ border: 1.5px dashed var(--border-strong); border-radius: var(--radius); padding: 2rem 1.5rem; text-align: center; cursor: pointer; transition: background 0.15s, border-color 0.15s; background: var(--bg); }}
# .drop-zone:hover, .drop-zone.drag-over {{ background: var(--accent-bg); border-color: var(--accent); }}
# .drop-zone p {{ font-size: 13px; color: var(--text-muted); margin: 0; }}
# .drop-zone small {{ font-size: 11px; color: var(--text-hint); margin-top: 4px; display: block; }}
# .file-list-wrap {{ display: flex; flex-direction: column; gap: 6px; margin-top: 1rem; }}
# .file-row {{ display: flex; align-items: center; gap: 10px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px 12px; }}
# .ext-badge {{ font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; flex-shrink: 0; }}
# .ext-pdf  {{ background: #faece7; color: #993c1d; }}
# .ext-txt  {{ background: #e6f1fb; color: #185fa5; }}
# .ext-docx {{ background: #eeedfe; color: #534ab7; }}
# .ext-md   {{ background: #eaf3de; color: #3b6d11; }}
# .ext-other{{ background: #f1efe8; color: #5f5e5a; }}
# .file-name {{ flex: 1; font-size: 13px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
# .file-size {{ font-size: 11px; color: var(--text-hint); flex-shrink: 0; }}
# .btn-remove {{ background: none; border: none; cursor: pointer; color: var(--text-hint); font-size: 16px; padding: 0 2px; line-height: 1; flex-shrink: 0; }}
# .btn-remove:hover {{ color: #a32d2d; }}
# .btn-upload {{ margin-top: 0.75rem; width: 100%; padding: 9px; background: var(--accent); color: #fff; border: none; border-radius: var(--radius-sm); font-size: 13px; font-weight: 500; cursor: pointer; transition: background 0.15s; }}
# .btn-upload:hover:not(:disabled) {{ background: var(--accent-hover); }}
# .btn-upload:disabled {{ opacity: 0.4; cursor: not-allowed; }}
# .existing-files {{ margin-top: 1.5rem; }}
# .existing-row {{ display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 13px; }}
# .existing-row:last-child {{ border-bottom: none; }}
# .del-btn {{ margin-left: auto; background: none; border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 3px 10px; font-size: 11px; color: var(--text-muted); cursor: pointer; }}
# .del-btn:hover {{ background: var(--error-bg); color: var(--error-text); border-color: var(--error-text); }}

# ::-webkit-scrollbar {{ width: 5px; }}
# ::-webkit-scrollbar-track {{ background: transparent; }}
# ::-webkit-scrollbar-thumb {{ background: var(--border-strong); border-radius: 10px; }}
# </style>
# </head>
# <body>

# <header>
#   <div class="av-dot">{avatar_initials}</div>
#   <div>
#     <div class="av-name">{avatar_name}</div>
#     <div class="av-role">{role_label}</div>
#   </div>
#   <div class="online"></div>
# </header>

# <div class="tabs">
#   <div class="tab active" onclick="showTab('chat',this)">Chat</div>
#   <div class="tab" onclick="showTab('personality',this)">Personality</div>
#   <div class="tab" onclick="showTab('files',this)">Files</div>
# </div>

# <!-- CHAT -->
# <div class="panel active" id="panel-chat">
#   <div class="messages" id="messageList">
#     <div class="msg bot">
#       <div class="msg-av">{avatar_initials}</div>
#       <div class="msg-bubble">{welcome}</div>
#     </div>
#   </div>
#   <div class="chat-input-row">
#     <textarea id="chat-input" rows="1" placeholder="{placeholder}"></textarea>
#     <button class="send-btn" id="sendBtn">Send</button>
#   </div>
#   <div class="chat-hint">Enter to send &nbsp;&middot;&nbsp; Shift+Enter for new line</div>
# </div>

# <!-- PERSONALITY -->
# <div class="panel" id="panel-personality">
#   <div class="settings-body">
#     <div>
#       <span class="field-label">Role &amp; personality</span>
#       <textarea class="persona-box" id="personaBox" placeholder="Describe how your avatar should behave...">{avatar_persona}</textarea>
#     </div>
#     <div style="display:flex;align-items:center;gap:12px;">
#       <button class="btn-save" onclick="savePersona()">Save changes</button>
#       <span class="status-msg" id="personaStatus"></span>
#     </div>
#     <div style="font-size:12px;color:var(--text-hint);line-height:1.6;border-top:1px solid var(--border);padding-top:1rem;">
#       Tip: Describe the avatar's role, tone, and any rules it should follow.
#       Changes take effect on the next message sent in Chat.
#     </div>
#   </div>
# </div>

# <!-- FILES -->
# <div class="panel" id="panel-files">
#   <div class="settings-body">
#     <div>
#       <div class="drop-zone" id="dropZone">
#         <p>Drop files or click to add more documents</p>
#         <small>PDF &middot; TXT &middot; DOCX &middot; MD</small>
#         <input type="file" id="fileInput" multiple accept=".pdf,.txt,.docx,.md" style="display:none" />
#       </div>
#       <div class="file-list-wrap" id="newFileList"></div>
#       <button class="btn-upload" id="uploadBtn" disabled onclick="uploadFiles()">Upload &amp; index files</button>
#       <span class="status-msg" id="uploadStatus" style="margin-top:8px;"></span>
#     </div>

#     <div class="existing-files">
#       <span class="field-label">Indexed documents</span>
#       <div id="existingFiles">
#         {_render_existing_files(avatar_files, avatar_id)}
#       </div>
#     </div>
#   </div>
# </div>

# <script>
# const AVATAR_ID = "{avatar_id}";
# const INITIALS  = "{avatar_initials}";
# const BACKEND   = "http://localhost:8000";
# let newFiles    = [];

# /* ── Tabs ── */
# function showTab(name, el) {{
#   document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
#   document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
#   el.classList.add("active");
#   document.getElementById("panel-" + name).classList.add("active");
# }}

# /* ── Markdown strip + escape ── */
# function strip(t) {{
#   return t.replace(/\\*\\*(.+?)\\*\\*/g,"$1").replace(/\\*(.+?)\\*/g,"$1")
#     .replace(/#+\\s+/g,"").replace(/^[-*]\\s+/gm,"")
#     .replace(/`(.+?)`/g,"$1").trim();
# }}
# function esc(s) {{
#   return strip(s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
#     .replace(/>/g,"&gt;").replace(/\\n/g,"<br>");
# }}

# /* ── Chat ── */
# const msgList = document.getElementById("messageList");
# const input   = document.getElementById("chat-input");
# const sendBtn = document.getElementById("sendBtn");

# function addMsg(role, text) {{
#   const d  = document.createElement("div");
#   d.className = "msg " + role;
#   const av = `<div class="msg-av">${{role==="bot"?INITIALS:"Y"}}</div>`;
#   const b  = `<div class="msg-bubble ${{text==="..."?"typing":""}}">${{esc(text)}}</div>`;
#   d.innerHTML = role === "user" ? b+av : av+b;
#   msgList.appendChild(d);
#   msgList.scrollTop = msgList.scrollHeight;
#   return d;
# }}

# input.addEventListener("input", () => {{
#   input.style.height = "auto";
#   input.style.height = Math.min(input.scrollHeight, 120) + "px";
# }});
# input.addEventListener("keydown", e => {{
#   if (e.key === "Enter" && !e.shiftKey) {{ e.preventDefault(); sendMsg(); }}
# }});
# sendBtn.addEventListener("click", sendMsg);

# async function sendMsg() {{
#   const text = input.value.trim();
#   if (!text) return;
#   input.value = ""; input.style.height = "auto";
#   sendBtn.disabled = true;
#   addMsg("user", text);
#   const typing = addMsg("bot", "...");
#   try {{
#     const res  = await fetch(BACKEND + "/avatar/ask", {{
#       method: "POST",
#       headers: {{ "Content-Type": "application/json" }},
#       body: JSON.stringify({{ question: text, avatar_id: AVATAR_ID, n_results: 3 }})
#     }});
#     const data = await res.json();
#     typing.remove();
#     addMsg("bot", res.ok ? data.answer : (data.detail || "Something went wrong."));
#   }} catch {{
#     typing.remove();
#     addMsg("bot", "Could not reach the backend. Is the server running?");
#   }}
#   sendBtn.disabled = false;
#   input.focus();
# }}

# /* ── Personality ── */
# async function savePersona() {{
#   const persona = document.getElementById("personaBox").value.trim();
#   const st      = document.getElementById("personaStatus");
#   st.className  = "status-msg";
#   try {{
#     const form = new FormData();
#     form.append("name",      "{avatar_name}");
#     form.append("avatar_id", AVATAR_ID);
#     form.append("persona",   persona);
#     form.append("reset",     "false");
#     form.append("files",     new File(["placeholder"], "placeholder.txt", {{type:"text/plain"}}));
#     const res  = await fetch(BACKEND + "/avatar/upload", {{ method: "POST", body: form }});
#     if (res.ok) {{
#       st.textContent = "Saved. Changes apply to your next chat message.";
#       st.className   = "status-msg status-ok";
#     }} else {{
#       const d = await res.json();
#       st.textContent = d.detail?.message || d.detail || "Save failed.";
#       st.className   = "status-msg status-err";
#     }}
#   }} catch {{
#     st.textContent = "Could not reach backend.";
#     st.className   = "status-msg status-err";
#   }}
# }}

# /* ── Files ── */
# const dropZone  = document.getElementById("dropZone");
# const fileInput = document.getElementById("fileInput");
# const uploadBtn = document.getElementById("uploadBtn");

# dropZone.addEventListener("click", () => fileInput.click());
# fileInput.addEventListener("change", e => addNewFiles(Array.from(e.target.files)));
# dropZone.addEventListener("dragover", e => {{ e.preventDefault(); dropZone.classList.add("drag-over"); }});
# dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
# dropZone.addEventListener("drop", e => {{
#   e.preventDefault(); dropZone.classList.remove("drag-over");
#   addNewFiles(Array.from(e.dataTransfer.files));
# }});

# function getExt(name) {{ const m = name.match(/[.]([a-z0-9]+)$/i); return m ? m[1].toLowerCase() : "other"; }}
# function fmtBytes(b) {{
#   if (b < 1024) return b + " B";
#   if (b < 1048576) return (b/1024).toFixed(1) + " KB";
#   return (b/1048576).toFixed(1) + " MB";
# }}

# function addNewFiles(files) {{
#   const seen = new Set(newFiles.map(f => f.name + f.size));
#   files.forEach(f => {{ if (!seen.has(f.name + f.size)) newFiles.push(f); }});
#   renderNewFiles();
# }}

# function removeNewFile(i) {{ newFiles.splice(i,1); renderNewFiles(); }}

# function renderNewFiles() {{
#   const wrap = document.getElementById("newFileList");
#   wrap.innerHTML = "";
#   newFiles.forEach((f, i) => {{
#     const ext  = getExt(f.name);
#     const row  = document.createElement("div");
#     row.className = "file-row";
#     row.innerHTML = `
#       <span class="ext-badge ext-${{['pdf','txt','docx','md'].includes(ext)?ext:'other'}}">${{ext}}</span>
#       <span class="file-name">${{f.name}}</span>
#       <span class="file-size">${{fmtBytes(f.size)}}</span>
#       <button class="btn-remove" onclick="removeNewFile(${{i}})">&#215;</button>`;
#     wrap.appendChild(row);
#   }});
#   uploadBtn.disabled = newFiles.length === 0;
# }}

# async function uploadFiles() {{
#   const st = document.getElementById("uploadStatus");
#   uploadBtn.disabled = true;
#   uploadBtn.textContent = "Uploading...";
#   st.className = "status-msg";
#   const form = new FormData();
#   form.append("name",      "{avatar_name}");
#   form.append("avatar_id", AVATAR_ID);
#   form.append("persona",   document.getElementById("personaBox").value.trim());
#   form.append("reset",     "false");
#   newFiles.forEach(f => form.append("files", f));
#   try {{
#     const res  = await fetch(BACKEND + "/avatar/upload", {{ method: "POST", body: form }});
#     const data = await res.json();
#     if (res.ok) {{
#       st.textContent = `${{data.files_processed.length}} file(s) indexed. ${{data.total_chunks}} chunks added.`;
#       st.className   = "status-msg status-ok";
#       newFiles = [];
#       renderNewFiles();
#       loadExistingFiles();
#     }} else {{
#       st.textContent = data.detail?.message || data.detail || "Upload failed.";
#       st.className   = "status-msg status-err";
#     }}
#   }} catch {{
#     st.textContent = "Could not reach backend.";
#     st.className   = "status-msg status-err";
#   }}
#   uploadBtn.disabled = false;
#   uploadBtn.textContent = "Upload & index files";
# }}

# async function loadExistingFiles() {{
#   try {{
#     const res  = await fetch(BACKEND + "/avatars");
#     const data = await res.json();
#     const av   = data.avatars.find(a => a.id === AVATAR_ID);
#     if (!av) return;
#     const wrap = document.getElementById("existingFiles");
#     const files = av.files || [];
#     if (files.length === 0) {{
#       wrap.innerHTML = '<div style="font-size:12px;color:var(--text-hint);">No documents indexed yet.</div>';
#       return;
#     }}
#     wrap.innerHTML = files.map(f => {{
#       const ext = getExt(f);
#       return `<div class="existing-row">
#         <span class="ext-badge ext-${{['pdf','txt','docx','md'].includes(ext)?ext:'other'}}">${{ext}}</span>
#         <span style="font-size:13px;flex:1;">${{f}}</span>
#         <button class="del-btn" onclick="deleteAvatar()">Delete avatar</button>
#       </div>`;
#     }}).join("");
#   }} catch {{}}
# }}

# async function deleteAvatar() {{
#   if (!confirm("Delete this entire avatar and all its data? This cannot be undone.")) return;
#   try {{
#     await fetch(BACKEND + "/avatar/" + AVATAR_ID, {{ method: "DELETE" }});
#     document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;color:#6b6963;">Avatar deleted. You can close this window.</div>';
#   }} catch {{
#     alert("Could not reach backend.");
#   }}
# }}

# loadExistingFiles();
# </script>
# </body>
# </html>"""

#     buf = io.BytesIO()
#     with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:

#         # ── Backend ───────────────────────────────────────────────────
#         for fname in ["main.py", "ingest.py", "retriever.py", "llm.py", "__init__.py"]:
#             src = backend_dir / fname
#             if src.exists():
#                 zf.write(src, arcname=f"{repo_name}/backend/{fname}")

#         zf.writestr(f"{repo_name}/backend/.env.example",
#             "# Copy this to .env and fill in your real key\n"
#             "# Never commit .env to GitHub\n\n"
#             "OPENAI_API_KEY=sk-your-openai-api-key-here\n")

#         # ── Personalized frontend ─────────────────────────────────────
#         zf.writestr(f"{repo_name}/frontend/index.html", personalized_frontend)

#         # ── Avatar data ───────────────────────────────────────────────
#         for file_path in avatar_dir.rglob("*"):
#             if file_path.is_file():
#                 zf.write(file_path,
#                     arcname=f"{repo_name}/data/avatars/{avatar_id}/{file_path.relative_to(avatar_dir)}")
#         zf.writestr(f"{repo_name}/data/avatars/.gitkeep", "")

#         # ── requirements.txt ─────────────────────────────────────────
#         req = project_root / "requirements.txt"
#         if req.exists():
#             zf.write(req, arcname=f"{repo_name}/requirements.txt")
#         else:
#             zf.writestr(f"{repo_name}/requirements.txt",
#                 "fastapi\nuvicorn[standard]\npython-dotenv\nopenai\n"
#                 "pypdf\nfaiss-cpu\nsentence-transformers\nnumpy\n"
#                 "python-docx\npython-multipart\n")

#         # ── .gitignore ────────────────────────────────────────────────
#         zf.writestr(f"{repo_name}/.gitignore",
#             "__pycache__/\n*.py[cod]\nvenv/\nenv/\n.venv/\n"
#             "backend/.env\n.DS_Store\nThumbs.db\n.vscode/\n.idea/\n")

#         # ── README ────────────────────────────────────────────────────
#         readme = f"""# {avatar_name}

# > {role_label}

# Built with SMARTAvatar. Clone this repo, add your OpenAI key, and run.

# ## Quick start

# ```bash
# python -m venv venv
# source venv/bin/activate  # Windows: venv\\Scripts\\Activate.ps1
# python -m pip install -r requirements.txt
# cp backend/.env.example backend/.env
# # Edit backend/.env and add your OPENAI_API_KEY
# uvicorn backend.main:app --reload --port 8000
# # Open frontend/index.html in your browser
# ```

# ## What this is

# {avatar_name} is an AI avatar trained on {len(avatar_files)} document(s).
# {"Persona: " + avatar_persona[:200] + ("..." if len(avatar_persona) > 200 else "") if avatar_persona else ""}

# ## Stack

# FastAPI · FAISS · sentence-transformers · GPT-4o-mini · Vanilla HTML/CSS/JS
# """
#         zf.writestr(f"{repo_name}/README.md", readme)

#     buf.seek(0)
#     return StreamingResponse(
#         buf,
#         media_type="application/zip",
#         headers={"Content-Disposition": f"attachment; filename={repo_name}.zip"},
#     )


# @app.delete("/avatar/{avatar_id}")
# def delete_avatar(avatar_id: str):
#     reset_avatar(avatar_id)
#     return {"message": f"Avatar '{avatar_id}' deleted from memory and disk."}


# @app.get("/")
# def root():
#     return {
#         "message": "AI Digital Twin API v3 is running.",
#         "data_directory": str(DATA_ROOT),
#         "endpoints": {
#             "POST /avatar/upload":           "Upload documents — saves files + index to disk",
#             "POST /avatar/ask":              "Ask a question to an avatar",
#             "GET  /avatars":                 "List all avatars",
#             "GET  /avatar/{id}/download":    "Download avatar as .zip (shareable repo)",
#             "DELETE /avatar/{id}":           "Delete avatar from memory and disk",
#         }
#     }
#------------------------------------------------------------------------------------------------------
#Note: This part uses Gemini API
# backend/main.py

import io
import os
import json
import shutil
import logging
import zipfile
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List

from .ingest import load_file, SUPPORTED_EXTENSIONS
from .retriever import (
    add_document, search, list_avatars, reset_avatar,
    save_uploaded_file, load_all_avatars_from_disk,
    DATA_ROOT, _avatar_dir,
)
from .llm import generate_answer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Digital Twin API", version="3.0")

app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/app")
def serve_frontend():
    return FileResponse("frontend/index.html")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup: reload all saved avatars from disk ───────────────────────────────

@app.on_event("startup")
def startup_event():
    load_all_avatars_from_disk()
    logger.info(f"Loaded avatars from disk: {[a['id'] for a in list_avatars()]}")


# ── Models ────────────────────────────────────────────────────────────────────

class QuestionRequest(BaseModel):
    question: str
    avatar_id: str
    n_results: int = 3


class AnswerResponse(BaseModel):
    answer: str
    context: List[str]
    avatar_id: str


class UploadResponse(BaseModel):
    avatar_id: str
    avatar_name: str
    files_processed: List[str]
    files_failed: List[dict]
    total_chunks: int
    message: str


class AvatarListResponse(BaseModel):
    avatars: List[dict]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/avatar/upload", response_model=UploadResponse)
async def upload_avatar_documents(
    name: str = Form(...),
    avatar_id: str = Form(...),
    persona: str = Form(""),
    reset: bool = Form(False),
    files: List[UploadFile] = File(...),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    if reset:
        reset_avatar(avatar_id)
        logger.info(f"Avatar '{avatar_id}' reset.")

    files_processed, files_failed, total_chunks = [], [], 0

    for upload in files:
        filename = upload.filename or "unknown"
        try:
            file_bytes = await upload.read()
            text = load_file(filename, file_bytes)

            if not text.strip():
                files_failed.append({"file": filename, "reason": "Empty or unreadable file."})
                continue

            save_uploaded_file(file_bytes, filename, avatar_id)

            chunks_added = add_document(text, source=filename, avatar_id=avatar_id, name=name, persona=persona)
            total_chunks += chunks_added
            files_processed.append(filename)
            logger.info(f"Indexed '{filename}' → {chunks_added} chunks for '{avatar_id}'")

        except ValueError as e:
            files_failed.append({"file": filename, "reason": str(e)})
        except Exception as e:
            logger.error(f"Failed '{filename}': {e}")
            files_failed.append({"file": filename, "reason": str(e)})

    if not files_processed:
        raise HTTPException(status_code=422, detail={
            "message": "No files could be processed.",
            "failures": files_failed,
            "supported_types": list(SUPPORTED_EXTENSIONS),
        })

    return UploadResponse(
        avatar_id=avatar_id,
        avatar_name=name,
        files_processed=files_processed,
        files_failed=files_failed,
        total_chunks=total_chunks,
        message=f"Avatar '{name}' ready — {total_chunks} chunks from {len(files_processed)} file(s). Saved to disk.",
    )


@app.post("/avatar/ask", response_model=AnswerResponse)
def ask_avatar(request: QuestionRequest):
    from .retriever import get_or_create_avatar
    store = get_or_create_avatar(request.avatar_id)

    context_chunks = search(request.question, n_results=request.n_results, avatar_id=request.avatar_id)

    if not context_chunks:
        raise HTTPException(status_code=404,
            detail=f"No data found for avatar '{request.avatar_id}'. Upload documents first.")

    context = "\n\n".join(context_chunks)
    answer  = generate_answer(
        context,
        request.question,
        name=store.name,
        persona=store.persona,
    )

    return AnswerResponse(answer=answer, context=context_chunks, avatar_id=request.avatar_id)


@app.get("/avatars", response_model=AvatarListResponse)
def get_avatars():
    return AvatarListResponse(avatars=list_avatars())


def _render_existing_files(files: list, avatar_id: str) -> str:
    """Render existing indexed files as HTML rows for the downloaded frontend."""
    if not files:
        return '<div style="font-size:12px;color:#a09d96;">No documents indexed yet.</div>'
    rows = []
    for f in files:
        ext = f.rsplit(".", 1)[-1].lower() if "." in f else "other"
        ext_cls = ext if ext in ["pdf", "txt", "docx", "md"] else "other"
        rows.append(
            f'<div class="existing-row">'
            f'<span class="ext-badge ext-{ext_cls}">{ext}</span>'
            f'<span style="font-size:13px;flex:1;">{f}</span>'
            f'<button class="del-btn" onclick="deleteAvatar()">Delete avatar</button>'
            f'</div>'
        )
    return "".join(rows)


@app.get("/avatar/{avatar_id}/download")
def download_avatar(avatar_id: str):
    """
    Download a complete, ready-to-run GitHub repository zip
    with a frontend personalized to this specific avatar.
    """
    avatar_dir = _avatar_dir(avatar_id)
    if not avatar_dir.exists():
        raise HTTPException(status_code=404, detail=f"Avatar '{avatar_id}' not found.")

    project_root = Path(__file__).parent.parent
    backend_dir  = Path(__file__).parent
    repo_name    = avatar_id

    # Load avatar info
    from .retriever import get_or_create_avatar
    store          = get_or_create_avatar(avatar_id)
    avatar_name    = store.name
    avatar_persona = store.persona or ""
    avatar_files   = list(set(store.sources))
    avatar_initials = "".join([w[0] for w in avatar_name.split()][:2]).upper()

    # Derive a short role label for the subtitle — strip "You are X" phrasing
    role_label = "AI Digital Twin"
    if avatar_persona:
        # Try to extract a clean role from common persona patterns
        import re
        # Match "You are [a/an] <role>" → extract just the role part
        m = re.search(r"you are (?:a |an |the )?(.+?)(?:\.|,|for\b)", avatar_persona, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            # Clean it up — capitalise first letter, max 50 chars
            if len(candidate) <= 50:
                role_label = candidate[0].upper() + candidate[1:]
        # Fallback: if no pattern matched, keep default

    # Welcome message — just a natural greeting, never reads back the persona
    if avatar_persona:
        welcome = f"Hi! How can I help you today?"
    else:
        welcome = f"Hi! Ask me anything about my background and experience."

    # Derive a unique accent color from avatar name
    hue = sum(ord(c) for c in avatar_name) % 360
    accent           = f"hsl({hue}, 55%, 38%)"
    accent_bg        = f"hsl({hue}, 55%, 95%)"
    accent_text      = f"hsl({hue}, 55%, 25%)"
    accent_hover     = f"hsl({hue}, 55%, 32%)"
    avatar_bg_color  = f"hsl({hue}, 40%, 90%)"
    avatar_txt_color = f"hsl({hue}, 40%, 28%)"

    # Chat placeholder based on persona
    if "support" in avatar_persona.lower() or "customer" in avatar_persona.lower():
        placeholder = f"Ask {avatar_name} a question..."
    elif "sales" in avatar_persona.lower():
        placeholder = "What would you like to know?"
    else:
        placeholder = "Ask me anything..."

    personalized_frontend = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{avatar_name}</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  --bg: #f7f6f3; --surface: #ffffff; --border: #e2e0d8;
  --border-strong: #c8c6bc; --text: #1c1a16; --text-muted: #6b6963;
  --text-hint: #a09d96;
  --accent: {accent}; --accent-bg: {accent_bg}; --accent-text: {accent_text};
  --accent-hover: {accent_hover};
  --av-bg: {avatar_bg_color}; --av-text: {avatar_txt_color};
  --success-bg: #eaf3de; --success-text: #27500a;
  --error-bg: #fcebeb; --error-text: #791f1f;
  --radius: 10px; --radius-sm: 6px;
  --font: 'Segoe UI', system-ui, -apple-system, sans-serif;
}}
body {{ font-family: var(--font); background: var(--bg); color: var(--text); height: 100vh; display: flex; flex-direction: column; overflow: hidden; }}

/* header */
header {{ display: flex; align-items: center; gap: 12px; padding: 0 1.5rem; height: 52px; background: var(--surface); border-bottom: 1px solid var(--border); flex-shrink: 0; }}
.av-dot {{ width: 32px; height: 32px; border-radius: 50%; background: var(--av-bg); color: var(--av-text); font-size: 12px; font-weight: 600; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }}
.av-name {{ font-size: 15px; font-weight: 600; color: var(--text); }}
.av-role {{ font-size: 12px; color: var(--text-hint); }}
.online {{ width: 8px; height: 8px; border-radius: 50%; background: #4caf50; margin-left: auto; }}

/* tabs */
.tabs {{ display: flex; gap: 0; border-bottom: 1px solid var(--border); background: var(--surface); flex-shrink: 0; padding: 0 1.5rem; }}
.tab {{ padding: 10px 18px; font-size: 13px; font-weight: 500; color: var(--text-muted); cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.15s; user-select: none; }}
.tab:hover {{ color: var(--text); }}
.tab.active {{ color: var(--accent); border-bottom-color: var(--accent); }}

/* panels */
.panel {{ display: none; flex: 1; overflow: hidden; flex-direction: column; }}
.panel.active {{ display: flex; }}

/* chat */
.messages {{ flex: 1; overflow-y: auto; padding: 1.5rem; display: flex; flex-direction: column; gap: 1rem; }}
.msg {{ display: flex; gap: 10px; max-width: 78%; }}
.msg.user {{ align-self: flex-end; flex-direction: row-reverse; }}
.msg.bot  {{ align-self: flex-start; }}
.msg-av {{ width: 30px; height: 30px; border-radius: 50%; font-size: 11px; font-weight: 600; display: flex; align-items: center; justify-content: center; flex-shrink: 0; margin-top: 2px; }}
.msg.bot  .msg-av {{ background: var(--av-bg); color: var(--av-text); }}
.msg.user .msg-av {{ background: var(--accent-bg); color: var(--accent-text); }}
.msg-bubble {{ padding: 9px 13px; border-radius: var(--radius); font-size: 13px; line-height: 1.6; }}
.msg.bot  .msg-bubble {{ background: var(--surface); border: 1px solid var(--border); color: var(--text); border-top-left-radius: 3px; }}
.msg.user .msg-bubble {{ background: var(--accent); color: #fff; border-top-right-radius: 3px; }}
.msg-bubble.typing {{ color: var(--text-hint); font-style: italic; }}
.chat-input-row {{ padding: 1rem 1.5rem; background: var(--surface); border-top: 1px solid var(--border); display: flex; gap: 10px; align-items: flex-end; flex-shrink: 0; }}
#chat-input {{ flex: 1; padding: 9px 12px; font-size: 13px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--bg); color: var(--text); outline: none; resize: none; max-height: 120px; line-height: 1.5; font-family: var(--font); transition: border-color 0.15s; }}
#chat-input:focus {{ border-color: var(--accent); background: var(--surface); }}
.send-btn {{ padding: 9px 18px; background: var(--accent); color: #fff; border: none; border-radius: var(--radius-sm); font-size: 13px; font-weight: 500; cursor: pointer; transition: background 0.15s; flex-shrink: 0; }}
.send-btn:hover:not(:disabled) {{ background: var(--accent-hover); }}
.send-btn:disabled {{ opacity: 0.35; cursor: not-allowed; }}
.chat-hint {{ font-size: 11px; color: var(--text-hint); text-align: center; padding: 0 0 0.5rem; }}

/* settings / files shared */
.settings-body {{ flex: 1; overflow-y: auto; padding: 2rem; max-width: 600px; width: 100%; margin: 0 auto; display: flex; flex-direction: column; gap: 1.5rem; }}
.field-label {{ font-size: 12px; color: var(--text-muted); margin-bottom: 6px; display: block; font-weight: 500; }}
textarea.persona-box {{ width: 100%; padding: 10px 12px; font-size: 13px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--bg); color: var(--text); outline: none; resize: vertical; min-height: 160px; font-family: var(--font); line-height: 1.6; transition: border-color 0.15s; }}
textarea.persona-box:focus {{ border-color: var(--accent); background: var(--surface); }}
.btn-save {{ padding: 9px 20px; background: var(--accent); color: #fff; border: none; border-radius: var(--radius-sm); font-size: 13px; font-weight: 500; cursor: pointer; transition: background 0.15s; }}
.btn-save:hover {{ background: var(--accent-hover); }}
.status-msg {{ font-size: 12px; padding: 8px 12px; border-radius: var(--radius-sm); display: none; }}
.status-ok  {{ background: var(--success-bg); color: var(--success-text); display: block; }}
.status-err {{ background: var(--error-bg);   color: var(--error-text);   display: block; }}

/* files panel */
.drop-zone {{ border: 1.5px dashed var(--border-strong); border-radius: var(--radius); padding: 2rem 1.5rem; text-align: center; cursor: pointer; transition: background 0.15s, border-color 0.15s; background: var(--bg); }}
.drop-zone:hover, .drop-zone.drag-over {{ background: var(--accent-bg); border-color: var(--accent); }}
.drop-zone p {{ font-size: 13px; color: var(--text-muted); margin: 0; }}
.drop-zone small {{ font-size: 11px; color: var(--text-hint); margin-top: 4px; display: block; }}
.file-list-wrap {{ display: flex; flex-direction: column; gap: 6px; margin-top: 1rem; }}
.file-row {{ display: flex; align-items: center; gap: 10px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px 12px; }}
.ext-badge {{ font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; flex-shrink: 0; }}
.ext-pdf  {{ background: #faece7; color: #993c1d; }}
.ext-txt  {{ background: #e6f1fb; color: #185fa5; }}
.ext-docx {{ background: #eeedfe; color: #534ab7; }}
.ext-md   {{ background: #eaf3de; color: #3b6d11; }}
.ext-other{{ background: #f1efe8; color: #5f5e5a; }}
.file-name {{ flex: 1; font-size: 13px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.file-size {{ font-size: 11px; color: var(--text-hint); flex-shrink: 0; }}
.btn-remove {{ background: none; border: none; cursor: pointer; color: var(--text-hint); font-size: 16px; padding: 0 2px; line-height: 1; flex-shrink: 0; }}
.btn-remove:hover {{ color: #a32d2d; }}
.btn-upload {{ margin-top: 0.75rem; width: 100%; padding: 9px; background: var(--accent); color: #fff; border: none; border-radius: var(--radius-sm); font-size: 13px; font-weight: 500; cursor: pointer; transition: background 0.15s; }}
.btn-upload:hover:not(:disabled) {{ background: var(--accent-hover); }}
.btn-upload:disabled {{ opacity: 0.4; cursor: not-allowed; }}
.existing-files {{ margin-top: 1.5rem; }}
.existing-row {{ display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 13px; }}
.existing-row:last-child {{ border-bottom: none; }}
.del-btn {{ margin-left: auto; background: none; border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 3px 10px; font-size: 11px; color: var(--text-muted); cursor: pointer; }}
.del-btn:hover {{ background: var(--error-bg); color: var(--error-text); border-color: var(--error-text); }}

::-webkit-scrollbar {{ width: 5px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: var(--border-strong); border-radius: 10px; }}

/* setup banner */
.setup-banner {{ background: #fffbeb; border-bottom: 1px solid #f0d080; padding: 10px 1.5rem; display: flex; align-items: center; gap: 12px; flex-shrink: 0; font-size: 12px; color: #7a5800; }}
.setup-banner strong {{ font-weight: 600; }}
.setup-banner input {{ font-size: 12px; padding: 4px 8px; border: 1px solid #d0b060; border-radius: 4px; background: #fffdf0; color: #3a2800; outline: none; width: 200px; }}
.setup-banner button {{ padding: 4px 12px; background: #c8880a; color: white; border: none; border-radius: 4px; font-size: 12px; cursor: pointer; white-space: nowrap; }}
.setup-banner button:hover {{ background: #a06a00; }}
.setup-banner .dismiss {{ margin-left: auto; cursor: pointer; color: #a08020; font-size: 16px; line-height: 1; background: none; border: none; }}
.setup-ok  {{ background: #eaf3de; border-color: #a0c870; color: #2a5000; }}
</style>
</head>
<body>

<header>
  <div class="av-dot">{avatar_initials}</div>
  <div>
    <div class="av-name">{avatar_name}</div>
    <div class="av-role">{role_label}</div>
  </div>
  <div class="online"></div>
</header>

<!-- SETUP BANNER — shown until backend is confirmed running -->
<div class="setup-banner" id="setupBanner">
  <div>
    <strong>Setup required:</strong> Start your backend server first, then enter its URL below.
    <code style="background:#fff8dc;padding:1px 6px;border-radius:3px;font-size:11px;margin-left:4px;">uvicorn backend.main:app --reload --port 8000</code>
  </div>
  <input type="text" id="backendUrlInput" placeholder="http://localhost:8000" />
  <button onclick="checkBackend()">Connect</button>
  <button class="dismiss" onclick="dismissBanner()" title="Dismiss">&#215;</button>
</div>

<div class="tabs">
  <div class="tab active" onclick="showTab('chat',this)">Chat</div>
  <div class="tab" onclick="showTab('personality',this)">Personality</div>
  <div class="tab" onclick="showTab('files',this)">Files</div>
</div>

<!-- CHAT -->
<div class="panel active" id="panel-chat">
  <div class="messages" id="messageList">
    <div class="msg bot">
      <div class="msg-av">{avatar_initials}</div>
      <div class="msg-bubble">{welcome}</div>
    </div>
  </div>
  <div class="chat-input-row">
    <textarea id="chat-input" rows="1" placeholder="{placeholder}"></textarea>
    <button class="send-btn" id="sendBtn">Send</button>
  </div>
  <div class="chat-hint">Enter to send &nbsp;&middot;&nbsp; Shift+Enter for new line</div>
</div>

<!-- PERSONALITY -->
<div class="panel" id="panel-personality">
  <div class="settings-body">
    <div>
      <span class="field-label">Role &amp; personality</span>
      <textarea class="persona-box" id="personaBox" placeholder="Describe how your avatar should behave...">{avatar_persona}</textarea>
    </div>
    <div style="display:flex;align-items:center;gap:12px;">
      <button class="btn-save" onclick="savePersona()">Save changes</button>
      <span class="status-msg" id="personaStatus"></span>
    </div>
    <div style="font-size:12px;color:var(--text-hint);line-height:1.6;border-top:1px solid var(--border);padding-top:1rem;">
      Tip: Describe the avatar's role, tone, and any rules it should follow.
      Changes take effect on the next message sent in Chat.
    </div>
  </div>
</div>

<!-- FILES -->
<div class="panel" id="panel-files">
  <div class="settings-body">
    <div>
      <div class="drop-zone" id="dropZone">
        <p>Drop files or click to add more documents</p>
        <small>PDF &middot; TXT &middot; DOCX &middot; MD</small>
        <input type="file" id="fileInput" multiple accept=".pdf,.txt,.docx,.md" style="display:none" />
      </div>
      <div class="file-list-wrap" id="newFileList"></div>
      <button class="btn-upload" id="uploadBtn" disabled onclick="uploadFiles()">Upload &amp; index files</button>
      <span class="status-msg" id="uploadStatus" style="margin-top:8px;"></span>
    </div>

    <div class="existing-files">
      <span class="field-label">Indexed documents</span>
      <div id="existingFiles">
        {_render_existing_files(avatar_files, avatar_id)}
      </div>
    </div>
  </div>
</div>

<script>
const AVATAR_ID = "{avatar_id}";
const INITIALS  = "{avatar_initials}";
let newFiles    = [];

/* ── Backend URL — saved per user, not hardcoded ── */
const STORAGE_KEY = "smartavatar_backend_url_{avatar_id}";
let BACKEND = localStorage.getItem(STORAGE_KEY) || "http://localhost:8000";
document.getElementById("backendUrlInput").value = BACKEND;

async function checkBackend() {{
  const rawInput = document.getElementById("backendUrlInput").value.trim();
  const input = rawInput.endsWith("/") ? rawInput.slice(0,-1) : rawInput;
  const banner = document.getElementById("setupBanner");
  try {{
    const res = await fetch(input + "/avatars", {{ signal: AbortSignal.timeout(4000) }});
    if (res.ok) {{
      BACKEND = input;
      localStorage.setItem(STORAGE_KEY, BACKEND);
      banner.className = "setup-banner setup-ok";
      banner.innerHTML = `
        <span>Connected to <strong>${{BACKEND}}</strong></span>
        <button class="dismiss" onclick="dismissBanner()" style="margin-left:auto;">&#215;</button>`;
      loadExistingFiles();
    }} else {{
      showBannerError(banner, "Server responded but returned an error. Is it the right URL?");
    }}
  }} catch {{
    showBannerError(banner, "Could not connect. Make sure the server is running and the URL is correct.");
  }}
}}

function showBannerError(banner, msg) {{
  banner.querySelector("button:not(.dismiss)").textContent = "Retry";
  const err = banner.querySelector(".banner-err") || document.createElement("span");
  err.className = "banner-err";
  err.style.cssText = "color:#a03000;font-size:11px;margin-left:8px;";
  err.textContent = msg;
  if (!banner.querySelector(".banner-err")) banner.appendChild(err);
}}

function dismissBanner() {{
  document.getElementById("setupBanner").style.display = "none";
}}

/* Check on load — if we already have a saved URL, test it silently */
(async () => {{
  try {{
    const res = await fetch(BACKEND + "/avatars", {{ signal: AbortSignal.timeout(3000) }});
    if (res.ok) {{
      dismissBanner();
      loadExistingFiles();
    }}
  }} catch {{ /* show banner, user needs to connect */ }}
}})();

/* ── Tabs ── */
function showTab(name, el) {{
  document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  el.classList.add("active");
  document.getElementById("panel-" + name).classList.add("active");
}}

/* ── Markdown strip + escape ── */
function strip(t) {{
  return t.replace(/\\*\\*(.+?)\\*\\*/g,"$1").replace(/\\*(.+?)\\*/g,"$1")
    .replace(/#+\\s+/g,"").replace(/^[-*]\\s+/gm,"")
    .replace(/`(.+?)`/g,"$1").trim();
}}
function esc(s) {{
  return strip(s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/\\n/g,"<br>");
}}

/* ── Chat ── */
const msgList = document.getElementById("messageList");
const input   = document.getElementById("chat-input");
const sendBtn = document.getElementById("sendBtn");

function addMsg(role, text) {{
  const d  = document.createElement("div");
  d.className = "msg " + role;
  const av = `<div class="msg-av">${{role==="bot"?INITIALS:"Y"}}</div>`;
  const b  = `<div class="msg-bubble ${{text==="..."?"typing":""}}">${{esc(text)}}</div>`;
  d.innerHTML = role === "user" ? b+av : av+b;
  msgList.appendChild(d);
  msgList.scrollTop = msgList.scrollHeight;
  return d;
}}

input.addEventListener("input", () => {{
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 120) + "px";
}});
input.addEventListener("keydown", e => {{
  if (e.key === "Enter" && !e.shiftKey) {{ e.preventDefault(); sendMsg(); }}
}});
sendBtn.addEventListener("click", sendMsg);

async function sendMsg() {{
  const text = input.value.trim();
  if (!text) return;
  input.value = ""; input.style.height = "auto";
  sendBtn.disabled = true;
  addMsg("user", text);
  const typing = addMsg("bot", "...");
  try {{
    const res  = await fetch(BACKEND + "/avatar/ask", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ question: text, avatar_id: AVATAR_ID, n_results: 3 }})
    }});
    const data = await res.json();
    typing.remove();
    addMsg("bot", res.ok ? data.answer : (data.detail || "Something went wrong."));
  }} catch {{
    typing.remove();
    addMsg("bot", "Could not reach the backend. Is the server running?");
  }}
  sendBtn.disabled = false;
  input.focus();
}}

/* ── Personality ── */
async function savePersona() {{
  const persona = document.getElementById("personaBox").value.trim();
  const st      = document.getElementById("personaStatus");
  st.className  = "status-msg";
  try {{
    const form = new FormData();
    form.append("name",      "{avatar_name}");
    form.append("avatar_id", AVATAR_ID);
    form.append("persona",   persona);
    form.append("reset",     "false");
    form.append("files",     new File(["placeholder"], "placeholder.txt", {{type:"text/plain"}}));
    const res  = await fetch(BACKEND + "/avatar/upload", {{ method: "POST", body: form }});
    if (res.ok) {{
      st.textContent = "Saved. Changes apply to your next chat message.";
      st.className   = "status-msg status-ok";
    }} else {{
      const d = await res.json();
      st.textContent = d.detail?.message || d.detail || "Save failed.";
      st.className   = "status-msg status-err";
    }}
  }} catch {{
    st.textContent = "Could not reach backend.";
    st.className   = "status-msg status-err";
  }}
}}

/* ── Files ── */
const dropZone  = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
const uploadBtn = document.getElementById("uploadBtn");

dropZone.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", e => addNewFiles(Array.from(e.target.files)));
dropZone.addEventListener("dragover", e => {{ e.preventDefault(); dropZone.classList.add("drag-over"); }});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", e => {{
  e.preventDefault(); dropZone.classList.remove("drag-over");
  addNewFiles(Array.from(e.dataTransfer.files));
}});

function getExt(name) {{ const m = name.match(/[.]([a-z0-9]+)$/i); return m ? m[1].toLowerCase() : "other"; }}
function fmtBytes(b) {{
  if (b < 1024) return b + " B";
  if (b < 1048576) return (b/1024).toFixed(1) + " KB";
  return (b/1048576).toFixed(1) + " MB";
}}

function addNewFiles(files) {{
  const seen = new Set(newFiles.map(f => f.name + f.size));
  files.forEach(f => {{ if (!seen.has(f.name + f.size)) newFiles.push(f); }});
  renderNewFiles();
}}

function removeNewFile(i) {{ newFiles.splice(i,1); renderNewFiles(); }}

function renderNewFiles() {{
  const wrap = document.getElementById("newFileList");
  wrap.innerHTML = "";
  newFiles.forEach((f, i) => {{
    const ext  = getExt(f.name);
    const row  = document.createElement("div");
    row.className = "file-row";
    row.innerHTML = `
      <span class="ext-badge ext-${{['pdf','txt','docx','md'].includes(ext)?ext:'other'}}">${{ext}}</span>
      <span class="file-name">${{f.name}}</span>
      <span class="file-size">${{fmtBytes(f.size)}}</span>
      <button class="btn-remove" onclick="removeNewFile(${{i}})">&#215;</button>`;
    wrap.appendChild(row);
  }});
  uploadBtn.disabled = newFiles.length === 0;
}}

async function uploadFiles() {{
  const st = document.getElementById("uploadStatus");
  uploadBtn.disabled = true;
  uploadBtn.textContent = "Uploading...";
  st.className = "status-msg";
  const form = new FormData();
  form.append("name",      "{avatar_name}");
  form.append("avatar_id", AVATAR_ID);
  form.append("persona",   document.getElementById("personaBox").value.trim());
  form.append("reset",     "false");
  newFiles.forEach(f => form.append("files", f));
  try {{
    const res  = await fetch(BACKEND + "/avatar/upload", {{ method: "POST", body: form }});
    const data = await res.json();
    if (res.ok) {{
      st.textContent = `${{data.files_processed.length}} file(s) indexed. ${{data.total_chunks}} chunks added.`;
      st.className   = "status-msg status-ok";
      newFiles = [];
      renderNewFiles();
      loadExistingFiles();
    }} else {{
      st.textContent = data.detail?.message || data.detail || "Upload failed.";
      st.className   = "status-msg status-err";
    }}
  }} catch {{
    st.textContent = "Could not reach backend.";
    st.className   = "status-msg status-err";
  }}
  uploadBtn.disabled = false;
  uploadBtn.textContent = "Upload & index files";
}}

async function loadExistingFiles() {{
  try {{
    const res  = await fetch(BACKEND + "/avatars");
    const data = await res.json();
    const av   = data.avatars.find(a => a.id === AVATAR_ID);
    const wrap = document.getElementById("existingFiles");
    if (!av || (av.files||[]).length === 0) {{
      wrap.innerHTML = '<div style="font-size:12px;color:var(--text-hint);">No documents indexed yet.</div>';
      return;
    }}
    wrap.innerHTML = av.files.map(f => {{
      const ext = getExt(f);
      const safe = encodeURIComponent(f);
      return `<div class="existing-row" id="row-${{safe}}">
        <span class="ext-badge ext-${{['pdf','txt','docx','md'].includes(ext)?ext:'other'}}">${{ext}}</span>
        <span style="font-size:13px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${{f}}</span>
        <button class="del-btn" onclick="deleteFile('${{f}}', '${{safe}}')">Remove</button>
      </div>`;
    }}).join("");
  }} catch {{}}
}}

async function deleteFile(filename, safeId) {{
  if (!confirm(`Remove "${{filename}}" from this avatar's knowledge base?`)) return;
  const btn = document.querySelector(`#row-${{safeId}} .del-btn`);
  if (btn) {{ btn.disabled = true; btn.textContent = "Removing..."; }}
  try {{
    const res  = await fetch(
      BACKEND + "/avatar/" + AVATAR_ID + "/file?filename=" + encodeURIComponent(filename),
      {{ method: "DELETE" }}
    );
    const data = await res.json();
    if (res.ok) {{
      const row = document.getElementById("row-" + safeId);
      if (row) row.remove();
      const st = document.getElementById("uploadStatus");
      st.textContent = data.message;
      st.className   = "status-msg status-ok";
      if ((data.remaining_files||[]).length === 0) {{
        document.getElementById("existingFiles").innerHTML =
          '<div style="font-size:12px;color:var(--text-hint);">No documents indexed yet.</div>';
      }}
    }} else {{
      alert(data.detail || "Could not remove file.");
      if (btn) {{ btn.disabled = false; btn.textContent = "Remove"; }}
    }}
  }} catch {{
    alert("Could not reach backend.");
    if (btn) {{ btn.disabled = false; btn.textContent = "Remove"; }}
  }}
}}

loadExistingFiles();
</script>
</body>
</html>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:

        # ── Backend ───────────────────────────────────────────────────
        for fname in ["main.py", "ingest.py", "retriever.py", "llm.py", "__init__.py"]:
            src = backend_dir / fname
            if src.exists():
                zf.write(src, arcname=f"{repo_name}/backend/{fname}")

        zf.writestr(f"{repo_name}/backend/.env.example",
            "# Copy this to .env and add your Gemini API key\n"
            "# Never commit .env to GitHub\n"
            "# Get a FREE key at: https://aistudio.google.com/app/apikey\n\n"
            "GEMINI_API_KEY=your-gemini-api-key-here\n")

        # ── Personalized frontend ─────────────────────────────────────
        zf.writestr(f"{repo_name}/frontend/index.html", personalized_frontend)

        # ── Avatar data ───────────────────────────────────────────────
        for file_path in avatar_dir.rglob("*"):
            if file_path.is_file():
                zf.write(file_path,
                    arcname=f"{repo_name}/data/avatars/{avatar_id}/{file_path.relative_to(avatar_dir)}")
        zf.writestr(f"{repo_name}/data/avatars/.gitkeep", "")

        # ── requirements.txt ─────────────────────────────────────────
        req = project_root / "requirements.txt"
        if req.exists():
            zf.write(req, arcname=f"{repo_name}/requirements.txt")
        else:
            zf.writestr(f"{repo_name}/requirements.txt",
                "fastapi\nuvicorn[standard]\npython-dotenv\ngoogle-generativeai\n"
                "pypdf\nfaiss-cpu\nsentence-transformers\nnumpy\n"
                "python-docx\npython-multipart\n")

        # ── .gitignore ────────────────────────────────────────────────
        zf.writestr(f"{repo_name}/.gitignore",
            "__pycache__/\n*.py[cod]\nvenv/\nenv/\n.venv/\n"
            "backend/.env\n.DS_Store\nThumbs.db\n.vscode/\n.idea/\n")

        # ── README ────────────────────────────────────────────────────
        readme = f"""# {avatar_name}

> {role_label}

AI avatar built with [SMARTAvatar](https://github.com/your-username/SMARTAvatar).
Trained on {len(avatar_files)} document(s): {", ".join(avatar_files) if avatar_files else "see data/avatars/"}

---

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Add your OpenAI key
cp backend/.env.example backend/.env
# then edit backend/.env

# 3. Run
uvicorn backend.main:app --reload --port 8000

# 4. Open frontend/index.html in your browser
```

## Stack

FastAPI · FAISS · sentence-transformers · GPT-4o-mini
"""
        zf.writestr(f"{repo_name}/README.md", readme)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={repo_name}.zip"},
    )


@app.delete("/avatar/{avatar_id}")
def delete_avatar(avatar_id: str):
    reset_avatar(avatar_id)
    return {"message": f"Avatar '{avatar_id}' deleted from memory and disk."}


@app.delete("/avatar/{avatar_id}/file")
def delete_avatar_file(avatar_id: str, filename: str):
    """
    Remove a single document from an avatar.
    - Deletes the file from data/avatars/<id>/files/
    - Rebuilds the FAISS index from remaining files
    - Saves updated chunks.json, index.faiss, and avatar.json to disk
    """
    from .retriever import (
        get_or_create_avatar, _save_avatar,
        chunk_text, embed
    )
    import faiss
    import numpy as np

    avatar_dir = _avatar_dir(avatar_id)
    files_dir  = avatar_dir / "files"
    target     = files_dir / filename

    if not avatar_dir.exists():
        raise HTTPException(status_code=404, detail=f"Avatar '{avatar_id}' not found.")
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found in avatar.")

    # Step 1 — delete physical file from disk
    target.unlink()
    logger.info(f"Deleted file '{filename}' from '{avatar_id}'")

    # Step 2 — reset in-memory index
    store         = get_or_create_avatar(avatar_id)
    store.index   = faiss.IndexFlatL2(384)
    store.docs    = []
    store.sources = []

    # Step 3 — re-index all remaining files from disk
    remaining = [f for f in files_dir.glob("*") if f.is_file()] if files_dir.exists() else []

    for file_path in remaining:
        try:
            from .ingest import load_file
            text = load_file(file_path.name, file_path.read_bytes())
            if not text.strip():
                continue
            chunks = chunk_text(text)
            for chunk in chunks:
                vector = embed(chunk)
                store.index.add(np.array([vector]))
                store.docs.append(chunk)
                store.sources.append(file_path.name)
            logger.info(f"Re-indexed '{file_path.name}' — {len(chunks)} chunks")
        except Exception as e:
            logger.warning(f"Could not re-index '{file_path.name}': {e}")

    # Step 4 — save everything back to disk
    # This updates chunks.json, index.faiss, and avatar.json
    _save_avatar(store)
    logger.info(f"Avatar '{avatar_id}' saved — {len(store.docs)} chunks from {len(remaining)} file(s)")

    return {
        "message": f"'{filename}' removed and index rebuilt.",
        "remaining_files": [f.name for f in remaining],
        "total_chunks": len(store.docs),
    }


@app.get("/")
def root():
    return {
        "message": "AI Digital Twin API v3 is running.",
        "data_directory": str(DATA_ROOT),
        "endpoints": {
            "POST /avatar/upload":           "Upload documents — saves files + index to disk",
            "POST /avatar/ask":              "Ask a question to an avatar",
            "GET  /avatars":                 "List all avatars",
            "GET  /avatar/{id}/download":    "Download avatar as .zip (shareable repo)",
            "DELETE /avatar/{id}":           "Delete avatar from memory and disk",
        }
    }