# Genuine source notices — provenance

Each file records one GENUINE public notice used in the genuine evaluation set (`evaluation/genuine.py`):
the URL, when and how it was captured, and the captured text.

**How the text was captured.** The build environment's shell cannot reach public sites (proxy policy), but the
session's web-fetch tool can read many of them. That tool returns a transcription of the page or PDF — verbatim quotes
(each at most ~125 characters) plus paraphrased structure — not the original HTML or PDF bytes. The evaluation
documents were therefore rebuilt from the captured transcription (every quoted sentence kept exactly as captured),
rendered as HTML, as an HTML table or as a PDF according to the original's form. The pipeline read those rebuilt
documents, not the live pages. The expected results were checked by a person against the captured text.

**What this is and is not.** The notices are genuine (real issuers, references, dates, criteria and wording); the
documents are reconstructions of them; the extractor is scripted (no AI provider key was available). The measured
numbers therefore show how the validation, identity, deadline, geography, contradiction and coverage logic behaves on
real wording, with the reconstruction caveat above. They do not measure the configured AI extractor and they do not
show market coverage.

Captured on 27 October 2026 (Asia/Dubai).

**Additions of 27 October 2026 (second instruction, item 7).** g14–g19 cover the five capability areas that had no
genuine example (trucking gateways, capacity and lanes, network development, forwarder sales, account growth). Where the
tool returned paraphrase rather than a full sentence (g14, g16), the rebuilt sentence joins the verbatim fragments with
the paraphrased structure; the file for each notice marks which parts are verbatim. They were captured after the rules of
that instruction were tuned and evaluated once.

**Original source documents.** Not added. The instruction asks for the originals "where permitted": the shell of the
build environment cannot download from these sites (every route goes through the egress allowlist; the publishers'
hosts are not on it), and the web-fetch tool returns transcriptions, not files. No publisher permission to redistribute
was established either. To add originals, download them in an environment with access, check each publisher's terms,
and store them under `genuine_sources/originals/` with their SHA-256.

**Tuning status.** g01–g13 were used to tune rules in two rounds (run 1 → reserved-right fix; the label corrections and
fixes of the second 27 Oct instruction) and are now regression cases. g14–g19 are untuned.
