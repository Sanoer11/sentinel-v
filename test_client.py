"""gnani_client retries: a retried upload must send the WHOLE audio again (bug found 4 Nov)."""
import requests
import gnani_client as g


def test_retry_resends_the_whole_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GNANI_API_KEY", "x")
    monkeypatch.setattr(g.time, "sleep", lambda s: None)
    sent = []

    class R:
        def __init__(self, code):
            self.status_code, self.text = code, ""

        def json(self):
            return {"success": True, "transcript": "ok"}

    def post(url, headers, timeout, **kw):
        body = requests.Request("POST", url, files=kw["files"]).prepare().body
        sent.append(b"AUDIO" in body)
        if len(sent) == 1:
            return R(429)
        if len(sent) == 2:
            raise requests.exceptions.ReadTimeout("slow")
        return R(200)
    monkeypatch.setattr(g.requests, "post", post)
    p = tmp_path / "a.wav"
    p.write_bytes(b"AUDIO")
    assert g.stt(str(p), "pilot") == "ok" and sent == [True, True, True]
