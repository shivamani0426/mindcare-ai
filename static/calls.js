/* Consent-based one-to-one calls. WebRTC handles audio/video; MindCare stores
   only expiring signaling messages, never the media itself. */
(() => {
  'use strict';
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const room = document.getElementById('video-call-room');
  const incoming = document.getElementById('incoming-call');
  const api = async (url, method = 'GET', payload = null) => {
    const options = {method, credentials: 'same-origin', cache: 'no-store', headers: {}};
    if (method !== 'GET') options.headers['X-CSRF-Token'] = csrf;
    if (payload) {options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(payload);}
    const response = await fetch(url, options);
    if (!response.ok) {const error = Error(`Request failed (${response.status})`); error.status = response.status; throw error;}
    return response.json();
  };

  // The main dashboard and all other signed-in pages can display a caregiver's
  // incoming call. A caregiver must deliberately accept it; no camera starts here.
  if (incoming && !room) {
    let currentId = null;
    let polling = false;
    const label = incoming.querySelector('#incoming-caller');
    const answer = incoming.querySelector('#incoming-answer');
    const decline = incoming.querySelector('#incoming-decline');
    const update = async () => {
      if (document.hidden || polling) return;
      polling = true;
      try {
        const result = await api('/api/calls/incoming');
        const call = result.calls?.[0];
        if (!call) { currentId = null; incoming.hidden = true; return; }
        const isNew = currentId !== call.id;
        currentId = call.id;
        if (isNew) window.MindCareVoice?.announce?.(`Video call from ${call.from}. Tap answer to talk.`, 12000);
        label.textContent = call.from;
        answer.href = call.url;
        incoming.hidden = false;
      } catch (_) { /* Do not show private notification when signed out. */ }
      finally {polling = false;}
    };
    decline?.addEventListener('click', async () => {
      if (!currentId) return;
      const id = currentId;
      incoming.hidden = true;
      currentId = null;
      try {await api(`/api/calls/${encodeURIComponent(id)}/decline`, 'POST');}
      catch (_) {update();}
    });
    update();
    document.addEventListener('visibilitychange', () => {if (!document.hidden) update();});
    setInterval(update, 4000);
  }
  if (!room) return;

  const token = room.dataset.callId;
  const base = `/api/calls/${encodeURIComponent(token)}`;
  const caller = room.dataset.caller === '1';
  const peerName = room.querySelector('h1')?.textContent.replace(/^Video call with\s*/, '') || 'your loved one';
  const statusText = document.getElementById('call-status-text');
  const localVideo = document.getElementById('local-video');
  const remoteVideo = document.getElementById('remote-video');
  const localPlaceholder = document.getElementById('local-placeholder');
  const remotePlaceholder = document.getElementById('remote-placeholder');
  const cameraButton = document.getElementById('call-camera');
  const micButton = document.getElementById('call-mic');
  const retryButton = document.getElementById('call-retry');
  const endButton = document.getElementById('call-hangup');
  const terminal = new Set(['ended', 'declined', 'expired']);
  const iceServers = [{urls: 'stun:stun.l.google.com:19302'}];
  if (room.dataset.turnUrl) {
    iceServers.push({urls: room.dataset.turnUrl,
      username: room.dataset.turnUser || '', credential: room.dataset.turnPassword || ''});
  }
  let peer = null;
  let stream = null;
  let lastEventId = 0;
  let pendingIce = [];
  let ready = false;
  let starting = false;
  let stopped = false;
  let connecting = false;
  let offerProcessed = false;
  let pollBusy = false;
  let polling = null;
  const status = (msg) => {statusText.textContent = msg;};

  function teardown() {
    if (stopped) return;
    stopped = true;
    if (polling) clearInterval(polling);
    window.MindCareVoice?.resume?.();
    try {peer?.close();} catch (_) {}
    stream?.getTracks().forEach(t => t.stop());
    localVideo.srcObject = null;
    remoteVideo.srcObject = null;
    localPlaceholder.hidden = false;
    remotePlaceholder.hidden = false;
    micButton.disabled = true;
    cameraButton.disabled = true;
    retryButton.hidden = true;
    endButton.textContent = 'Return to dashboard';
  }
  async function hangup() {
    if (!stopped) {
      teardown();
      status('The call has ended. Thank you for connecting.');
      try {await api(`${base}/end`, 'POST');} catch (_) {}
    } else window.location.assign('/dashboard');
  }
  endButton?.addEventListener('click', hangup);
  window.addEventListener('pagehide', () => {
    if (stopped) return;
    // sendBeacon does not support CSRF headers. A keepalive fetch does.
    try {fetch(`${base}/end`, {method:'POST', keepalive:true, credentials:'same-origin',
      headers:{'X-CSRF-Token': csrf}});} catch (_) {}
    teardown();
  });
  micButton?.addEventListener('click', () => {
    const track = stream?.getAudioTracks()[0];
    if (!track) return;
    track.enabled = !track.enabled;
    micButton.textContent = track.enabled ? '🎙️ Microphone on' : '🔇 Microphone off';
    micButton.setAttribute('aria-pressed', String(!track.enabled));
  });
  cameraButton?.addEventListener('click', () => {
    const track = stream?.getVideoTracks()[0];
    if (!track) return;
    track.enabled = !track.enabled;
    cameraButton.textContent = track.enabled ? '📷 Camera on' : '🚫 Camera off';
    cameraButton.setAttribute('aria-pressed', String(!track.enabled));
  });
  retryButton?.addEventListener('click', () => {retryButton.hidden = true; begin();});

  async function sendSignal(kind, payload) {
    if (!stopped) await api(`${base}/signal`, 'POST', {kind,payload});
  }
  async function flushCandidates() {
    if (!peer?.remoteDescription) return;
    const queued = pendingIce;
    pendingIce = [];
    for (const item of queued) {
      try {await peer.addIceCandidate(new RTCIceCandidate(item));} catch (_) { /* Old ICE can be ignored. */ }
    }
  }
  async function processEvent(event) {
    if (!peer || stopped) return;
    if (event.kind === 'candidate') {
      if (peer.remoteDescription) {
        try {await peer.addIceCandidate(new RTCIceCandidate(event.payload));} catch (_) {}
      } else pendingIce.push(event.payload);
    } else if (event.kind === 'offer' && !caller && !offerProcessed) {
      offerProcessed = true;
      await peer.setRemoteDescription(new RTCSessionDescription(event.payload));
      await flushCandidates();
      const answer = await peer.createAnswer();
      await peer.setLocalDescription(answer);
      await sendSignal('answer', {type:answer.type,sdp:answer.sdp});
      status(`Connecting you to ${peerName}…`);
    } else if (event.kind === 'answer' && caller && !peer.remoteDescription) {
      await peer.setRemoteDescription(new RTCSessionDescription(event.payload));
      await flushCandidates();
      status(`Connecting you to ${peerName}…`);
    }
  }
  async function tick() {
    if (stopped || pollBusy || document.hidden) return;
    pollBusy = true;
    try {
      const result = await api(`${base}/events?after=${lastEventId}`);
      if (terminal.has(result.status)) {
        teardown();
        status(result.status === 'declined' ? 'Your loved one cannot answer right now.' :
          result.status === 'expired' ? 'The call timed out. You can try again.' : 'The other person ended the call.');
        return;
      }
      if (ready) {
        for (const item of (result.events || [])) {
          await processEvent(item);
          lastEventId = Math.max(lastEventId, item.id);
        }
      }
      if (caller && result.status === 'ringing' && peer?.connectionState !== 'connected') {
        status(`Calling ${peerName}… Waiting for them to answer.`);
      }
    } catch (error) {
      if ([401,403,404].includes(error.status)) {teardown(); status('Access to this call has ended.');}
      else if (!stopped) status('Checking the connection…');
    } finally {pollBusy = false;}
  }
  async function begin() {
    if (stopped || starting || ready) return;
    starting = true;
    window.MindCareVoice?.pause?.();
    status('Please allow your camera and microphone when your browser asks.');
    try {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia || !window.RTCPeerConnection) {
        throw Error('Video calling requires a current browser on HTTPS with camera support.');
      }
      stream = await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},
        video:{facingMode:'user',width:{ideal:960},height:{ideal:540}}});
      if (stopped) {stream.getTracks().forEach(t => t.stop()); return;}
      localVideo.srcObject = stream;
      localPlaceholder.hidden = true;
      micButton.disabled = false;
      cameraButton.disabled = false;
      peer = new RTCPeerConnection({iceServers});
      stream.getTracks().forEach(track => peer.addTrack(track,stream));
      peer.addEventListener('track', event => {
        remoteVideo.srcObject = event.streams[0] || new MediaStream([event.track]);
        remotePlaceholder.hidden = true;
        remoteVideo.play().catch(() => status('Tap your video to enable sound.'));
      });
      remoteVideo.addEventListener('click',()=>remoteVideo.play().catch(()=>{}));
      peer.addEventListener('icecandidate', event => {
        if (event.candidate) sendSignal('candidate',event.candidate.toJSON()).catch(()=>{});
      });
      peer.addEventListener('connectionstatechange', () => {
        if (stopped) return;
        if (peer.connectionState === 'connected') status(`You are connected with ${peerName}. Enjoy your chat!`);
        else if (peer.connectionState === 'failed') status('The direct connection failed. This network may need a TURN relay. Please try another network.');
        else if (peer.connectionState === 'disconnected') status('Connection interrupted. Attempting to reconnect…');
      });
      ready = true;
      if (caller) {
        const offer = await peer.createOffer();
        await peer.setLocalDescription(offer);
        await sendSignal('offer',{type:offer.type,sdp:offer.sdp});
        status(`Calling ${peerName}… Waiting for them to answer.`);
      } else {
        await api(`${base}/accept`,'POST');
        status(`Joining the video call with ${peerName}…`);
      }
      tick();
    } catch (error) {
      if (!stopped) {
        status(error?.name === 'NotAllowedError' ?
          'Camera or microphone permission was denied. You can allow access in your browser and try again.' :
          error.message || 'Could not start your camera and microphone.');
        retryButton.hidden = false;
        ready = false;
        try {peer?.close();} catch (_) {}
        peer = null;
        stream?.getTracks().forEach(t => t.stop());
        stream = null;
      }
    } finally {starting = false;}
  }
  if (terminal.has(room.dataset.callStatus)) {
    status('This call has already ended. Start a new call from the dashboard.');
    teardown();
  } else {
    pollBusy = false;
    polling = setInterval(tick, 1800);
    begin();
  }
})();
