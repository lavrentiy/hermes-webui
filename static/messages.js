     1|async function send(){
     2|  const text=$('msg').value.trim();
     3|  if(!text&&!S.pendingFiles.length)return;
     4|  // Slash command intercept -- local commands handled without agent round-trip
     5|  if(text.startsWith('/')&&!S.pendingFiles.length&&executeCommand(text)){
     6|    $('msg').value='';autoResize();hideCmdDropdown();return;
     7|  }
     8|  // Don't send while an inline message edit is active
     9|  if(document.querySelector('.msg-edit-area'))return;
    10|  // If busy, queue the message instead of dropping it
    11|  if(S.busy){
    12|    if(text){
    13|      MSG_QUEUE.push(text);
    14|      $('msg').value='';autoResize();
    15|      updateQueueBadge();
    16|      showToast(`Queued: "${text.slice(0,40)}${text.length>40?'\u2026':''}"`,2000);
    17|    }
    18|    return;
    19|  }
    20|  if(!S.session){await newSession();await renderSessionList();}
    21|
    22|  const activeSid=S.session.session_id;
    23|
    24|  setStatus(S.pendingFiles&&S.pendingFiles.length?'Uploading…':'Sending…');
    25|  let uploaded=[];
    26|  try{uploaded=await uploadPendingFiles();}
    27|  catch(e){if(!text){setStatus(`❌ ${e.message}`);return;}}
    28|
    29|  let msgText=text;
    30|  if(uploaded.length&&!msgText)msgText=`I've uploaded ${uploaded.length} file(s): ${uploaded.join(', ')}`;
    31|  else if(uploaded.length)msgText=`${text}\n\n[Attached files: ${uploaded.join(', ')}]`;
    32|  if(!msgText){setStatus('Nothing to send');return;}
    33|
    34|  $('msg').value='';autoResize();
    35|  const displayText=text||(uploaded.length?`Uploaded: ${uploaded.join(', ')}`:'(file upload)');
    36|  const userMsg={role:'user',content:displayText,attachments:uploaded.length?uploaded:undefined,_ts:Date.now()/1000};
    37|  S.toolCalls=[];  // clear tool calls from previous turn
    38|  clearLiveToolCards();  // clear any leftover live cards from last turn
    39|  S.messages.push(userMsg);renderMessages();appendThinking();setBusy(true);  // activity bar shown via setBusy
    40|  INFLIGHT[activeSid]={messages:[...S.messages],uploaded};
    41|  startApprovalPolling(activeSid);
    42|  S.activeStreamId = null;  // will be set after stream starts
    43|
    44|  // Set provisional title from user message immediately so session appears
    45|  // in the sidebar right away with a meaningful name (server may refine later)
    46|  if(S.session&&(S.session.title==='Untitled'||!S.session.title)){
    47|    const provisionalTitle=displayText.slice(0,64);
    48|    S.session.title=provisionalTitle;
    49|    syncTopbar();
    50|    // Persist it and refresh the sidebar now -- don't wait for done
    51|    api('/api/session/rename',{method:'POST',body:JSON.stringify({
    52|      session_id:activeSid, title:provisionalTitle
    53|    })}).catch(()=>{});  // fire-and-forget, server refines on done
    54|    renderSessionList();  // session appears in sidebar immediately
    55|  } else {
    56|    renderSessionList();  // ensure it's visible even if already titled
    57|  }
    58|
    59|  // Start the agent via POST, get a stream_id back
    60|  let streamId;
    61|  try{
    62|    const startData=await api('/api/chat/start',{method:'POST',body:JSON.stringify({
    63|      session_id:activeSid,message:msgText,
    64|      model:S.session.model||$('modelSelect').value,workspace:S.session.workspace,
    65|      attachments:uploaded.length?uploaded:undefined
    66|    })});
    67|    streamId=startData.stream_id;
    68|    S.activeStreamId = streamId;
    69|    markInflight(activeSid, streamId);
    70|    // Show Cancel button
    71|    const cancelBtn=$('btnCancel');
    72|    if(cancelBtn) cancelBtn.style.display='';
    73|  }catch(e){
    74|    delete INFLIGHT[activeSid];
    75|    stopApprovalPolling();
    76|    // Only hide approval card if it belongs to the session that just finished
    77|    if(!_approvalSessionId || _approvalSessionId===activeSid) hideApprovalCard();removeThinking();
    78|    S.messages.push({role:'assistant',content:`**Error:** ${e.message}`});
    79|    renderMessages();setBusy(false);setStatus('Error: '+e.message);
    80|    return;
    81|  }
    82|
    83|  // Open SSE stream and render tokens live
    84|  let assistantText='';
    85|  let assistantRow=null;
    86|  let assistantBody=null;
    87|
    88|  function ensureAssistantRow(){
    89|    if(assistantRow)return;
    90|    removeThinking();
    91|    const tr=$('toolRunningRow');if(tr)tr.remove();
    92|    $('emptyState').style.display='none';
    93|    assistantRow=document.createElement('div');assistantRow.className='msg-row';
    94|    assistantBody=document.createElement('div');assistantBody.className='msg-body';
    95|    const role=document.createElement('div');role.className='msg-role assistant';
    96|    const icon=document.createElement('div');icon.className='role-icon assistant';icon.textContent='H';
    97|    const lbl=document.createElement('span');lbl.style.fontSize='12px';lbl.textContent='Hermes';
    98|    role.appendChild(icon);role.appendChild(lbl);
    99|    assistantRow.appendChild(role);assistantRow.appendChild(assistantBody);
   100|    $('msgInner').appendChild(assistantRow);
   101|  }
   102|
   103|  // ── Shared SSE handler wiring (used for initial connection and reconnect) ──
   104|  let _reconnectAttempted=false;
   105|
   106|  // rAF-throttled rendering: buffer tokens, render at most once per frame
   107|  let _renderPending=false;
   108|  function _scheduleRender(){
   109|    if(_renderPending) return;
   110|    _renderPending=true;
   111|    requestAnimationFrame(()=>{
   112|      _renderPending=false;
   113|      if(assistantBody) assistantBody.innerHTML=renderMd(assistantText);
   114|      scrollIfPinned();
   115|    });
   116|  }
   117|
   118|  function _wireSSE(source){
   119|    source.addEventListener('token',e=>{
   120|      if(!S.session||S.session.session_id!==activeSid) return;
   121|      const d=JSON.parse(e.data);
   122|      assistantText+=d.text;
   123|      ensureAssistantRow();
   124|      _scheduleRender();
   125|    });
   126|
   127|    source.addEventListener('tool',e=>{
   128|      const d=JSON.parse(e.data);
   129|      if(S.session&&S.session.session_id===activeSid){
   130|        setStatus(`${d.name}${d.preview?' · '+d.preview.slice(0,55):''}`);
   131|      }
   132|      if(!S.session||S.session.session_id!==activeSid) return;
   133|      removeThinking();
   134|      const oldRow=$('toolRunningRow');if(oldRow)oldRow.remove();
   135|      const tc={name:d.name, preview:d.preview||'', args:d.args||{}, snippet:'', done:false};
   136|      S.toolCalls.push(tc);
   137|      appendLiveToolCard(tc);
   138|      scrollIfPinned();
   139|    });
   140|
   141|    source.addEventListener('approval',e=>{
   142|      const d=JSON.parse(e.data);
   143|      d._session_id=activeSid;
   144|      showApprovalCard(d);
   145|    });
   146|
   147|    source.addEventListener('done',e=>{
   148|      source.close();
   149|      const d=JSON.parse(e.data);
   150|      delete INFLIGHT[activeSid];
   151|      clearInflight();
   152|      stopApprovalPolling();
   153|      if(!_approvalSessionId || _approvalSessionId===activeSid) hideApprovalCard();
   154|      if(S.session&&S.session.session_id===activeSid){
   155|        S.activeStreamId=null;
   156|        const _cb=$('btnCancel');if(_cb)_cb.style.display='none';
   157|      }
   158|      if(S.session&&S.session.session_id===activeSid){
   159|        S.session=d.session;S.messages=d.session.messages||[];
   160|        // Stamp _ts on the last assistant message if it has no timestamp
   161|        const lastAsst=[...S.messages].reverse().find(m=>m.role==='assistant');
   162|        if(lastAsst&&!lastAsst._ts&&!lastAsst.timestamp) lastAsst._ts=Date.now()/1000;
   163|        if(d.usage){S.lastUsage=d.usage;_syncCtxIndicator(d.usage);}
   164|        if(d.session.tool_calls&&d.session.tool_calls.length){
   165|          S.toolCalls=d.session.tool_calls.map(tc=>({...tc,done:true}));
   166|        } else {
   167|          S.toolCalls=S.toolCalls.map(tc=>({...tc,done:true}));
   168|        }
   169|        if(uploaded.length){
   170|          const lastUser=[...S.messages].reverse().find(m=>m.role==='user');
   171|          if(lastUser)lastUser.attachments=uploaded;
   172|        }
   173|        clearLiveToolCards();
   174|        S.busy=false;
   175|        syncTopbar();renderMessages();loadDir('.');
   176|      }
   177|      renderSessionList();setBusy(false);setStatus('');
   178|    });
   179|
   180|    source.addEventListener('compressed',e=>{
   181|      // Context was auto-compressed during this turn -- show a system message
   182|      if(!S.session||S.session.session_id!==activeSid) return;
   183|      try{
   184|        const d=JSON.parse(e.data);
   185|        const sysMsg={role:'assistant',content:'*[Context was auto-compressed to continue the conversation]*'};
   186|        S.messages.push(sysMsg);
   187|        showToast(d.message||'Context compressed');
   188|      }catch(err){}
   189|    });
   190|
   191|    source.addEventListener('title',e=>{
      // LLM-generated title arrived asynchronously after done
      try{
        const d=JSON.parse(e.data);
        if(d.title&&d.session_id){
          // Update the in-memory session if it's the active one
          if(S.session&&S.session.session_id===d.session_id){
            S.session.title=d.title;
            syncTopbar();
          }
          // Always refresh sidebar so the renamed entry appears immediately
          renderSessionList();
        }
      }catch(_){}
    });

    source.addEventListener('apperror',e=>{
      // Application-level error sent explicitly by the server (rate limit, crash, etc.)
      // This is distinct from the SSE network 'error' event below.
   192|      source.close();
   193|      delete INFLIGHT[activeSid];clearInflight();stopApprovalPolling();
   194|      if(!_approvalSessionId||_approvalSessionId===activeSid) hideApprovalCard();
   195|      if(S.session&&S.session.session_id===activeSid){
   196|        S.activeStreamId=null;const _cbe=$('btnCancel');if(_cbe)_cbe.style.display='none';
   197|        clearLiveToolCards();if(!assistantText)removeThinking();
   198|        try{
   199|          const d=JSON.parse(e.data);
   200|          const isRateLimit=d.type==='rate_limit';
   201|          const icon=isRateLimit?'⏱️':'⚠️';
   202|          const label=isRateLimit?'Rate limit reached':'Error';
   203|          const hint=d.hint?`\n\n*${d.hint}*`:'';
   204|          S.messages.push({role:'assistant',content:`**${icon} ${label}:** ${d.message}${hint}`});
   205|        }catch(_){
   206|          S.messages.push({role:'assistant',content:'**⚠️ Error:** An error occurred. Check server logs.'});
   207|        }
   208|        renderMessages();
   209|      }else if(typeof trackBackgroundError==='function'){
   210|        const _errTitle=(typeof _allSessions!=='undefined'&&_allSessions.find(s=>s.session_id===activeSid)||{}).title||null;
   211|        try{const d=JSON.parse(e.data);trackBackgroundError(activeSid,_errTitle,d.message||'Error');}
   212|        catch(_){trackBackgroundError(activeSid,_errTitle,'Error');}
   213|      }
   214|      if(!S.session||!INFLIGHT[S.session.session_id]){setBusy(false);setStatus('');}
   215|    });
   216|
   217|    source.addEventListener('warning',e=>{
   218|      // Non-fatal warning from server (e.g. fallback activated, retrying)
   219|      if(!S.session||S.session.session_id!==activeSid) return;
   220|      try{
   221|        const d=JSON.parse(e.data);
   222|        // Show as a small inline notice, not a full error
   223|        setStatus(`⚠️ ${d.message||'Warning'}`);
   224|        // If it's a fallback notice, show it briefly then clear
   225|        if(d.type==='fallback') setTimeout(()=>setStatus(''),4000);
   226|      }catch(_){}
   227|    });
   228|
   229|    source.addEventListener('error',e=>{
   230|      source.close();
   231|      // Attempt one reconnect if the stream is still active server-side
   232|      if(!_reconnectAttempted && streamId){
   233|        _reconnectAttempted=true;
   234|        setStatus('Connection lost \u2014 reconnecting\u2026');
   235|        setTimeout(async()=>{
   236|          try{
   237|            const st=await api(`/api/chat/stream/status?stream_id=${encodeURIComponent(streamId)}`);
   238|            if(st.active){
   239|              setStatus('Reconnected');
   240|              _wireSSE(new EventSource(new URL(`/api/chat/stream?stream_id=${encodeURIComponent(streamId)}`,location.origin).href,{withCredentials:true}));
   241|              return;
   242|            }
   243|          }catch(_){}
   244|          _handleStreamError();
   245|        },1500);
   246|        return;
   247|      }
   248|      _handleStreamError();
   249|    });
   250|
   251|    source.addEventListener('cancel',e=>{
   252|      source.close();
   253|      delete INFLIGHT[activeSid];clearInflight();stopApprovalPolling();
   254|      if(!_approvalSessionId||_approvalSessionId===activeSid) hideApprovalCard();
   255|      if(S.session&&S.session.session_id===activeSid){
   256|        S.activeStreamId=null;const _cbc=$('btnCancel');if(_cbc)_cbc.style.display='none';
   257|      }
   258|      if(S.session&&S.session.session_id===activeSid){
   259|        clearLiveToolCards();if(!assistantText)removeThinking();
   260|        S.messages.push({role:'assistant',content:'*Task cancelled.*'});renderMessages();
   261|      }
   262|      renderSessionList();
   263|      if(!S.session||!INFLIGHT[S.session.session_id]){setBusy(false);setStatus('');}
   264|    });
   265|  }
   266|
   267|  function _handleStreamError(){
   268|    delete INFLIGHT[activeSid];clearInflight();stopApprovalPolling();
   269|    if(!_approvalSessionId||_approvalSessionId===activeSid) hideApprovalCard();
   270|    if(S.session&&S.session.session_id===activeSid){
   271|      S.activeStreamId=null;const _cbe=$('btnCancel');if(_cbe)_cbe.style.display='none';
   272|      clearLiveToolCards();if(!assistantText)removeThinking();
   273|      S.messages.push({role:'assistant',content:'**Error:** Connection lost'});renderMessages();
   274|    }else{
   275|      // User switched away — show background error banner
   276|      if(typeof trackBackgroundError==='function'){
   277|        // Look up session title from the session list cache so the banner names it correctly
   278|        const _errTitle=(typeof _allSessions!=='undefined'&&_allSessions.find(s=>s.session_id===activeSid)||{}).title||null;
   279|        trackBackgroundError(activeSid,_errTitle,'Connection lost');
   280|      }
   281|    }
   282|    if(!S.session||!INFLIGHT[S.session.session_id]){setBusy(false);setStatus('Error: Connection lost');}
   283|  }
   284|
   285|  _wireSSE(new EventSource(new URL(`/api/chat/stream?stream_id=${encodeURIComponent(streamId)}`,location.origin).href,{withCredentials:true}));
   286|
   287|}
   288|
   289|function transcript(){
   290|  const lines=[`# Hermes session ${S.session?.session_id||''}`,``,
   291|    `Workspace: ${S.session?.workspace||''}`,`Model: ${S.session?.model||''}`,``];
   292|  for(const m of S.messages){
   293|    if(!m||m.role==='tool')continue;
   294|    let c=m.content||'';
   295|    if(Array.isArray(c))c=c.filter(p=>p&&p.type==='text').map(p=>p.text||'').join('\n');
   296|    const ct=String(c).trim();
   297|    if(!ct&&!m.attachments?.length)continue;
   298|    const attach=m.attachments?.length?`\n\n_Files: ${m.attachments.join(', ')}_`:'';
   299|    lines.push(`## ${m.role}`,'',ct+attach,'');
   300|  }
   301|  return lines.join('\n');
   302|}
   303|
   304|function autoResize(){const el=$('msg');el.style.height='auto';el.style.height=Math.min(el.scrollHeight,200)+'px';updateSendBtn();}
   305|
   306|
   307|// ── Approval polling ──
   308|let _approvalPollTimer = null;
   309|
   310|// showApprovalCard moved above respondApproval
   311|
   312|function hideApprovalCard() {
   313|  $("approvalCard").classList.remove("visible");
   314|  $("approvalCmd").textContent = "";
   315|  $("approvalDesc").textContent = "";
   316|}
   317|
   318|// Track session_id of the active approval so respond goes to the right session
   319|let _approvalSessionId = null;
   320|
   321|function showApprovalCard(pending) {
   322|  $("approvalDesc").textContent = pending.description || "";
   323|  $("approvalCmd").textContent = pending.command || "";
   324|  const keys = pending.pattern_keys || (pending.pattern_key ? [pending.pattern_key] : []);
   325|  $("approvalDesc").textContent = (pending.description || "") + (keys.length ? " [" + keys.join(", ") + "]" : "");
   326|  _approvalSessionId = pending._session_id || (S.session && S.session.session_id) || null;
   327|  $("approvalCard").classList.add("visible");
   328|}
   329|
   330|async function respondApproval(choice) {
   331|  const sid = _approvalSessionId || (S.session && S.session.session_id);
   332|  if (!sid) return;
   333|  hideApprovalCard();
   334|  _approvalSessionId = null;
   335|  try {
   336|    await api("/api/approval/respond", {
   337|      method: "POST",
   338|      body: JSON.stringify({ session_id: sid, choice })
   339|    });
   340|  } catch(e) { setStatus("Approval error: " + e.message); }
   341|}
   342|
   343|function startApprovalPolling(sid) {
   344|  stopApprovalPolling();
   345|  _approvalPollTimer = setInterval(async () => {
   346|    if (!S.busy || !S.session || S.session.session_id !== sid) {
   347|      stopApprovalPolling(); hideApprovalCard(); return;
   348|    }
   349|    try {
   350|      const data = await api("/api/approval/pending?session_id=" + encodeURIComponent(sid));
   351|      if (data.pending) { data.pending._session_id=sid; showApprovalCard(data.pending); }
   352|      else { hideApprovalCard(); }
   353|    } catch(e) { /* ignore poll errors */ }
   354|  }, 1500);
   355|}
   356|
   357|function stopApprovalPolling() {
   358|  if (_approvalPollTimer) { clearInterval(_approvalPollTimer); _approvalPollTimer = null; }
   359|}
   360|// ── Panel navigation (Chat / Tasks / Skills / Memory) ──
   361|
   362|