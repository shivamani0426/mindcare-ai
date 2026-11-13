/* MindCare voice-only, account-free guest invitations.
   Only ephemeral signaling passes through Flask. Audio travels by WebRTC. */
(() => {
  'use strict';
  const room = document.getElementById('guest-voice-room');
  if (!room) return;
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const id = encodeURIComponent(room.dataset.callId || '');
  const caller = room.dataset.isPatient === '1';
  const token = room.dataset.inviteToken || '';
  const base = '/api/guest-voice/' + id;
  const statusNode = document.getElementById('guest-voice-status-text');
  const startBtn = document.getElementById('guest-voice-start');
  const muteBtn = document.getElementById('guest-voice-mute');
  const hearBtn = document.getElementById('guest-voice-hear');
  const endBtn = document.getElementById('guest-voice-end');
  const remoteAudio = document.getElementById('guest-voice-remote-audio');
  const copyBtn = document.getElementById('guest-voice-copy');
  const copyStatus = document.getElementById('guest-voice-copy-status');
  const terminal = new Set(['ended', 'expired', 'declined']);
  const iceServers = [{urls:'stun:stun.l.google.com:19302'}];
  if (room.dataset.turnUrl) {
    iceServers.push({urls:room.dataset.turnUrl,
      username:room.dataset.turnUser || '',credential:room.dataset.turnPassword || ''});
  }
  let pc = null;
  let micStream = null;
  let cursor = 0;
  let pendingCandidates = [];
  let active = false;
  let ended = false;
  let offerStarted = false;
  let offerReceived = false;
  let busy = false;
  let polling = null;
  let starting = false;
  const status = message => { if (statusNode) statusNode.textContent = message; };

  async function api(url, method = 'GET', body = null) {
    const options = {method, credentials:'same-origin', cache:'no-store', headers:{}};
    if (method !== 'GET') options.headers['X-CSRF-Token'] = csrf;
    if (body) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(body);
    }
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.error || 'Request failed (' + response.status + ')');
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function stopLocally() {
    if (ended) return;
    ended = true;
    active = false;
    if (polling) clearInterval(polling);
    try {pc?.close();} catch (_) {}
    micStream?.getTracks().forEach(t => t.stop());
    pc = null;
    micStream = null;
    if (remoteAudio) remoteAudio.srcObject = null;
    if (startBtn) startBtn.disabled = true;
    if (muteBtn) muteBtn.disabled = true;
    if (hearBtn) hearBtn.hidden = true;
    if (endBtn) endBtn.textContent = '← Back';
    window.MindCareVoice?.resume?.();
  }
  async function endCall() {
    if (ended) {
      window.location.assign(caller ? '/help' : '/');
      return;
    }
    stopLocally();
    status('The voice call has ended.');
    try { await api(base + '/end', 'POST'); } catch (_) {}
  }
  endBtn?.addEventListener('click', endCall);
  window.addEventListener('pagehide', () => {
    if (ended) return;
    // Keepalive supports CSRF; do not use sendBeacon for this endpoint.
    try {fetch(base + '/end', {method:'POST', credentials:'same-origin', keepalive:true,
      headers:{'X-CSRF-Token':csrf}});} catch (_) {}
    stopLocally();
  });

  copyBtn?.addEventListener('click', async () => {
    const url = copyBtn.dataset.url || '';
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      copyStatus.textContent = 'Invitation copied! Send it privately to your trusted contact.';
      copyBtn.textContent = '✓ Copied link';
    } catch (_) {
      try {
        const text = document.createElement('textarea');
        text.value = url;
        text.style.position = 'fixed';
        text.style.opacity = '0';
        document.body.appendChild(text);
        text.select();
        if (!document.execCommand('copy')) throw new Error('Copy failed');
        text.remove();
        copyStatus.textContent = 'Invitation copied! Send it privately.';
      } catch (_) {
        copyStatus.textContent = 'Copy is unavailable in this browser. Use the WhatsApp invitation button instead.';
      }
    }
  });

  muteBtn?.addEventListener('click', () => {
    const track = micStream?.getAudioTracks()[0];
    if (!track) return;
    track.enabled = !track.enabled;
    muteBtn.textContent = track.enabled ? '🎙️ Mute microphone' : '🔇 Unmute microphone';
    muteBtn.setAttribute('aria-pressed', String(!track.enabled));
  });
  hearBtn?.addEventListener('click', () => {
    remoteAudio?.play().then(() => {hearBtn.hidden = true;})
      .catch(() => status('Please check your device volume and audio permissions.'));
  });

  async function send(kind, payload) {
    if (!ended) await api(base + '/signal', 'POST', {kind,payload});
  }
  async function flushCandidates() {
    if (!pc?.remoteDescription) return;
    const queued = pendingCandidates;
    pendingCandidates = [];
    for (const candidate of queued) {
      try {await pc.addIceCandidate(new RTCIceCandidate(candidate));}
      catch (_) { /* Old or duplicated ICE candidate; ignore. */ }
    }
  }
  async function onEvent(event) {
    if (ended || !pc) return;
    if (event.kind === 'candidate') {
      if (pc.remoteDescription) {
        try {await pc.addIceCandidate(new RTCIceCandidate(event.payload));} catch (_) {}
      } else {
        pendingCandidates.push(event.payload);
      }
    } else if (event.kind === 'offer' && !caller && !offerReceived) {
      offerReceived = true;
      await pc.setRemoteDescription(new RTCSessionDescription(event.payload));
      await flushCandidates();
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      await send('answer', {type:answer.type, sdp:answer.sdp});
      status('Connecting your voice call…');
    } else if (event.kind === 'answer' && caller && !pc.remoteDescription) {
      await pc.setRemoteDescription(new RTCSessionDescription(event.payload));
      await flushCandidates();
      status('Connecting your voice call…');
    }
  }
  async function offer() {
    if (!caller || !active || !pc || offerStarted || ended) return;
    offerStarted = true;
    try {
      const offerDetails = await pc.createOffer();
      await pc.setLocalDescription(offerDetails);
      await send('offer', {type:offerDetails.type, sdp:offerDetails.sdp});
      status('Your invitation was answered. Connecting the microphones…');
    } catch (_) {
      status('Could not set up the voice connection. End this call and start a fresh one.');
    }
  }
  async function tick() {
    if (ended || busy || document.hidden) return;
    busy = true;
    try {
      const response = await api(base + '/events?after=' + cursor);
      if (terminal.has(response.status)) {
        stopLocally();
        status(response.status === 'expired' ? 'This invitation expired. Please start a new call.' :
          'The other person ended the voice call.');
        return;
      }
      if (!active) {
        status(response.status === 'accepted' ?
          'Your loved one has answered. Tap Enable microphone to talk.' :
          (caller ? 'Waiting for your loved one to open the link and answer…' :
            'Tap Answer voice call to enable your microphone.'));
        return;
      }
      if (caller && response.status === 'accepted') await offer();
      for (const event of (response.events || [])) {
        await onEvent(event);
        cursor = Math.max(cursor, event.id);
      }
    } catch (error) {
      if ([401, 403, 404].includes(error.status)) {
        stopLocally();
        status('You no longer have access to this invitation.');
      } else if (!ended) {
        status('Checking the call connection. Please check your internet.');
      }
    } finally {busy = false;}
  }

  async function begin() {
    if (ended || active || starting) return;
    starting = true;
    startBtn.disabled = true;
    window.MindCareVoice?.pause?.();
    status('Please allow microphone access when your browser asks.');
    try {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia || !window.RTCPeerConnection) {
        throw new Error('Voice calling needs HTTPS and a browser that supports WebRTC.');
      }
      // Request media directly in this button gesture. No camera is requested.
      const stream = await navigator.mediaDevices.getUserMedia({
        audio:{echoCancellation:true, noiseSuppression:true}, video:false
      });
      if (ended) {stream.getTracks().forEach(t => t.stop()); return;}
      micStream = stream;
      if (!caller) await api(base + '/join', 'POST', {invite_token:token});
      if (ended) {stream.getTracks().forEach(t => t.stop()); return;}
      pc = new RTCPeerConnection({iceServers});
      stream.getAudioTracks().forEach(track => pc.addTrack(track, stream));
      pc.addEventListener('track', event => {
        if (ended) return;
        remoteAudio.srcObject = event.streams[0] || new MediaStream([event.track]);
        remoteAudio.play().catch(() => {
          hearBtn.hidden = false;
          status('Voice connected. Tap “Tap to hear voice” to enable sound.');
        });
      });
      pc.addEventListener('icecandidate', event => {
        if (event.candidate) send('candidate', event.candidate.toJSON()).catch(() => {});
      });
      pc.addEventListener('connectionstatechange', () => {
        if (ended || !pc) return;
        if (pc.connectionState === 'connected') status('Connected! You can talk now. 💛');
        else if (pc.connectionState === 'failed') status(
          'The internet connection could not complete. A TURN relay may be needed on this network.');
        else if (pc.connectionState === 'disconnected') status(
          'Connection interrupted. Reconnecting…');
      });
      active = true;
      startBtn.hidden = true;
      muteBtn.disabled = false;
      status(caller ? 'Microphone ready. Waiting for your loved one to answer…' :
        'Microphone ready. Connecting you to your loved one…');
      await tick();
    } catch (error) {
      if (micStream) {micStream.getTracks().forEach(t => t.stop()); micStream = null;}
      try {pc?.close();} catch (_) {}
      pc = null;
      status(error?.name === 'NotAllowedError' ?
        'Microphone access was blocked. Allow your microphone in browser settings and try again.' :
        error.message || 'Cannot start this call. Please try again.');
      if (!ended) startBtn.disabled = false;
    } finally {
      starting = false;
    }
  }
  startBtn?.addEventListener('click', begin);
  if (terminal.has(room.dataset.callStatus)) {
    stopLocally();
    status('This voice call is no longer active. Please start a new one.');
  } else {
    polling = setInterval(tick, 1800);
    tick();
    document.addEventListener('visibilitychange', () => {if (!document.hidden) tick();});
  }
})();
