const CARD_TYPE = "rivian-gear-guard-card";

class RivianGearGuardCard extends HTMLElement {
  static getStubConfig(hass) {
    const ids = Object.keys(hass?.states || {});
    const camera =
      ids.find((id) => id.startsWith("camera.") && id.endsWith("_gear_guard_live")) ||
      "";
    const select =
      ids.find(
        (id) => id.startsWith("select.") && id.endsWith("_gear_guard_camera")
      ) || "";
    return { type: `custom:${CARD_TYPE}`, camera, select };
  }

  setConfig(config) {
    if (!config.camera || !config.select) {
      throw new Error("camera and select entity ids are required");
    }
    this._config = config;
  }

  set hass(hass) {
    const prev = this._selectState;
    this._hass = hass;
    const select = hass.states[this._config.select];
    const cam = select ? select.state : null;
    if (this._dc && this._dc.readyState === "open" && prev && cam && cam !== prev) {
      this._switchCamera(cam);
    }
    this._selectState = cam;
    this._render();
  }

  getCardSize() {
    return 6;
  }

  connectedCallback() {
    if (!this._root) {
      this._root = this.attachShadow({ mode: "open" });
    }
    this._render();
  }

  disconnectedCallback() {
    this._stop();
  }

  _render() {
    if (!this._root || !this._config) return;
    const cam = this._hass?.states?.[this._config.camera];
    const sel = this._hass?.states?.[this._config.select];
    const options = sel?.attributes?.options || [];
    const current = sel?.state || "";
    if (!this._built) {
      this._root.innerHTML = `
        <style>
          ha-card { padding: 12px; }
          video { width: 100%; background: #111; border-radius: 8px; min-height: 200px; }
          .row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
          button { cursor: pointer; }
          .status { font-size: 13px; opacity: 0.8; margin-top: 8px; }
        </style>
        <ha-card header="Gear Guard Live">
          <video playsinline autoplay muted></video>
          <div class="row" id="cams"></div>
          <div class="row">
            <button id="play">Play</button>
            <button id="stop">Stop</button>
          </div>
          <div class="status" id="status"></div>
        </ha-card>
      `;
      this._video = this._root.querySelector("video");
      this._status = this._root.querySelector("#status");
      this._cams = this._root.querySelector("#cams");
      this._root.querySelector("#play").addEventListener("click", () =>
        // Without this the card sits on "starting…" forever when _play throws.
        this._play().catch((err) => {
          this._busy = String(err?.message || err);
          this._render();
        })
      );
      this._root.querySelector("#stop").addEventListener("click", () => this._stop());
      this._built = true;
    }
    this._cams.innerHTML = "";
    for (const opt of options) {
      const btn = document.createElement("button");
      btn.textContent = opt;
      if (opt === current) btn.disabled = true;
      btn.addEventListener("click", () => this._pick(opt));
      this._cams.appendChild(btn);
    }
    const name = cam?.attributes?.friendly_name || this._config.camera;
    this._status.textContent = this._busy
      ? this._busy
      : `${name} · ${current || "—"}`;
  }

  async _pick(option) {
    if (!this._hass) return;
    await this._hass.callService("select", "select_option", {
      entity_id: this._config.select,
      option,
    });
  }

  async _switchCamera(camera) {
    if (!this._dc || this._dc.readyState !== "open") return;
    const msg = await this._hass.connection.sendMessagePromise({
      type: "rivian/gear_guard_switch_payload",
      camera,
    });
    const raw = Uint8Array.from(atob(msg.payload_b64), (c) => c.charCodeAt(0));
    this._dc.send(raw);
    this._busy = `switched to ${camera} (data channel)`;
    this._render();
  }

  async _iceServers() {
    // The vehicle's KVS relay only exists once the master session has been
    // started, which the offer does not do until the peer connection is
    // already built. gear_guard_prepare starts it first and answers in
    // get_client_config's own shape, so both branches below read one shape.
    try {
      const prep = await this._hass.connection.sendMessagePromise({
        type: "rivian/gear_guard_prepare",
        entity_id: this._config.camera,
      });
      return prep?.configuration?.iceServers || [];
    } catch (_err) {
      // Pointed at a camera that is not a Rivian live view: prepare rejects.
      // Degrade to stock HA WebRTC rather than leaving the card on "starting".
      const cfg = await this._hass.connection.sendMessagePromise({
        type: "camera/webrtc/get_client_config",
        entity_id: this._config.camera,
      });
      return cfg?.configuration?.iceServers || [];
    }
  }

  _preferH264(tx) {
    // KVS drops a signaling frame over 10000 bytes of encoded payload without
    // any error, and the vehicle then never answers. Offering everything the
    // browser supports — AV1, VP9, VP8, four H264 profiles, red, ulpfec, and
    // an rtx line for each — pushed the SDP past 7KB and over that limit.
    // The vehicle only ever answers H264, so the rest was padding that cost
    // us the session.
    try {
      const caps = RTCRtpReceiver.getCapabilities?.("video");
      if (!caps || !tx.setCodecPreferences) return;
      const wanted = caps.codecs.filter((c) => /H264|rtx/i.test(c.mimeType));
      if (wanted.length) tx.setCodecPreferences(wanted);
    } catch (_err) {
      // Older browsers: the offer stays large and the backend guard reports it.
    }
  }

  _sendCandidate(candidate) {
    this._hass.connection
      .sendMessagePromise({
        type: "camera/webrtc/candidate",
        entity_id: this._config.camera,
        session_id: this._sessionId,
        candidate: {
          candidate: candidate.candidate,
          sdpMid: candidate.sdpMid,
          sdpMLineIndex: candidate.sdpMLineIndex,
        },
      })
      .catch(() => {
        /* session already gone */
      });
  }

  async _play() {
    await this._stop();
    this._busy = "starting…";
    this._render();
    const iceServers = await this._iceServers();
    this._pc = new RTCPeerConnection({ iceServers });
    this._dc = this._pc.createDataChannel("data", { ordered: true });
    const tx = this._pc.addTransceiver("video", { direction: "recvonly" });
    this._preferH264(tx);
    this._pc.ontrack = (ev) => {
      if (this._video && ev.streams[0]) this._video.srcObject = ev.streams[0];
    };
    this._pc.onicecandidate = (ev) => {
      if (!ev.candidate) return;
      // Gathering finishes long before the offer subscription answers with a
      // session id. Dropping these strands the vehicle with no address to
      // send media to, so hold them and flush once the id arrives.
      if (!this._sessionId) {
        this._pending.push(ev.candidate);
        return;
      }
      this._sendCandidate(ev.candidate);
    };
    const offer = await this._pc.createOffer();
    await this._pc.setLocalDescription(offer);
    this._unsub = await this._hass.connection.subscribeMessage(
      (event) => this._onWebrtc(event),
      {
        type: "camera/webrtc/offer",
        entity_id: this._config.camera,
        offer: offer.sdp,
      }
    );
    await this._hass.connection.sendMessagePromise({
      type: "rivian/gear_guard_hold",
      entity_id: this._config.camera,
      hold: true,
    });
    this._busy = "live";
    this._render();
  }

  async _onWebrtc(event) {
    if (!event || !this._pc) return;
    if (event.type === "session") {
      this._sessionId = event.session_id;
      const held = this._pending;
      this._pending = [];
      for (const candidate of held) this._sendCandidate(candidate);
      return;
    }
    if (event.type === "answer" && event.answer) {
      await this._pc.setRemoteDescription({ type: "answer", sdp: event.answer });
      return;
    }
    if (event.type === "candidate" && event.candidate) {
      const c = event.candidate;
      const cand = typeof c === "string" ? c : c.candidate;
      if (!cand) return;
      await this._pc.addIceCandidate({
        candidate: cand,
        sdpMid: c.sdpMid ?? "0",
        sdpMLineIndex: c.sdpMLineIndex ?? 0,
      });
      return;
    }
    if (event.type === "error") {
      this._busy = event.message || event.code || "error";
      this._render();
    }
  }

  async _stop() {
    if (this._unsub) {
      try {
        this._unsub();
      } catch (_err) {
        /* already closed */
      }
      this._unsub = null;
    }
    if (this._hass && this._config) {
      try {
        await this._hass.connection.sendMessagePromise({
          type: "rivian/gear_guard_hold",
          entity_id: this._config.camera,
          hold: false,
        });
      } catch (_err) {
        /* hass going away */
      }
    }
    if (this._dc) {
      try {
        this._dc.close();
      } catch (_err) {
        /* already closed */
      }
      this._dc = null;
    }
    if (this._pc) {
      this._pc.close();
      this._pc = null;
    }
    this._sessionId = null;
    this._pending = [];
    if (this._video) this._video.srcObject = null;
    this._busy = "";
  }
}

if (!customElements.get(CARD_TYPE)) {
  customElements.define(CARD_TYPE, RivianGearGuardCard);
}
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === CARD_TYPE)) {
  window.customCards.push({
    type: CARD_TYPE,
    name: "Rivian Gear Guard Live",
    description: "Live view with APK data-channel camera switch",
  });
}
