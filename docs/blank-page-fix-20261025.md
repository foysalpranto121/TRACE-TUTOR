# Blank page repair — 2026-10-25

The live HTML referenced `/assets/index-gXmta9HV.js` and `/assets/index-DW4OBw9M.css`, both of which returned HTTP 404 despite being present on disk. API health remained OK.

WhiteNoise builds its static-file index when the application worker starts. The timing release restarted the worker before copying the new frontend assets, so new hashed filenames were absent from that index. Checking only the served HTML entry did not catch this failure.

After confirming the files existed, restarted `trace-tutor`. The entry JavaScript, React chunk, and CSS then returned HTTP 200 with the correct MIME types. Independently checked all 44 JavaScript/CSS files emitted by the release: zero failures, including lazy-loaded page chunks.

Updated `deploy_protocol_release.py` to publish all assets and the HTML index before restarting the worker, and verify every emitted JavaScript/CSS asset over HTTP before reporting success. No student records were modified by this repair.

Browser automation was unavailable in this session; visual rendering was not claimed as verified.
