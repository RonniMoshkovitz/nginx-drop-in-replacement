# nginx-drop-in-replacement
This project produces a drop-in replacement for `nginx:1.25-bookworm` with two CVEs eliminated (CVE-2024-6119 & CVE-2026-15176) using two different techniques, version bump and backport patch.
It runs a compatibility test against both the original `nginx:1.25-bookworm` and the rebuilt version to make sure it's a drop-in replacement. 
It also runs CVE scans on the new image, including VEX-based demonstration of scanner suppression for the backport.

## Build
**Requirements:**
  * Docker with BuildKit
  * `make`
  * Python 3 (to run the test scripts) 

> [!NOTE]
> The test scripts need a *host* with Python. Unlike `scan`/`scan-vex` below which run entirely inside containers, the python test scripts run locally on the *host* machine.

**Build & test:**
```bash
make all
```
Builds the `.deb`, builds the image, and runs all test suites in one command.

**Build image:**
```bash
make image
```
Runs the full build process, builds the patched `.deb` from source (`make deb`) and then the runtime image (`nginx-patched:1.25-bookworm`).

## Test & Scan
**Test:**
```bash
make test
```
Runs the compatibility and the CVE-2026-15176 tests.

**Scan:**
```bash
make scan
```
```bash
make scan-vex
```
Rescans the new image using `grype` and `trivy` (no need to install these)

## Image size
| Image | Size |
| :--- | :--- |
| `nginx:1.25-bookworm` (baseline) | 188MB |
| `nginx-patched:1.25-bookworm` (this build) | 189MB |

## Selected CVEs
To select the CVEs I used both the baseline scans on nginx:1.25-bookworm using [`grype`](reports/baseline-grype.txt) and [`trivy`](reports/baseline-trivy.txt), and an online research of the CVEs listed.
Combining these allowed me to choose CVEs based on data from the reports, along with the understanding of the functional risk each CVE created and the complexity of the fix.

**I chose to fix 2 main CVEs, each in a different technique:**

| CVE ID | Severity | Fix Method | Component | Current Version | Fixed Version | Evidence link |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| CVE-2024-6119 | High (CVSS 7.5) | bump | OpenSSL (`libssl3`/`openssl`) | `3.0.11-1~deb12u2` | `3.0.14-1~deb12u2` *see note below* | [Debian security tracker](https://security-tracker.debian.org/tracker/CVE-2024-6119) |
| CVE-2026-15176 | Critical (Grype) / Medium (nginx's own advisory) | backport | nginx `ngx_http_core_module` | `1.25.5-1~bookworm` | backported from `1.30.6`/`1.31.7` | [upstream commit](https://github.com/nginx/nginx/commit/f8a23425bd6840c4c36b4264edf576ba3646156f) |

> [!NOTE]
> This project uses `3.0.22-1~deb12u2`, as it's the current resolvable `bookworm-security` release (`3.0.14-1~deb12u2` is no longer available)

**Version bump pick:** 
* CVE-2024-6119 - I chose this CVE because OpenSSL is a real dependency nginx actively links (`ngx_http_ssl_module`), with an official Debian fix already available, and is high severity.

**Backport pick:** 
* CVE-2026-15176 - I chose this CVE because it was both high severity and had a one-line upstream fix I could verify and apply with zero conflicts.

## Compatibility test
[test/compatibility_test.py](test/compatibility_test.py) boots `nginx:1.25-bookworm` and `nginx-patched:1.25-bookworm` as separate containers and issues an identical request matrix at both.

**This includes:**

* `GET /` & `GET /does-not-exist` (the second one resulting in a 404)
* `HEAD /`
* `POST /` with 256KiB and 2MiB bodies.
* A raw-socket malformed HTTP/1.1 request with no `Host` header (`GET / HTTP/1.1\r\n\r\n`)
* `GET /ping` & `GET /status` against the containers with a bind-mounted custom [`conf file`](test/config/nginx.conf)


**"Working correctly" means:**

for every case above, status code, response body (byte-for-byte),
and headers match exactly (*see note below*) between the two images. Any mismatch raises `SystemExit` immediately and exits with a non-zero exit on the first failure.

> [!NOTE]
> headers matching excludes `Date`, `Connection`, `Keep-Alive` which legitimately differ per request or per process

## Rescan & VEX

```bash
make scan        # rescans the patched image
make scan-vex    # reruns both scanners with vex/nginx-cve-2026-15176.openvex.json applied
```

**Diff against the baseline:**

| Scanner | Baseline | Patched |
| :--- | :--- | :--- |
| Trivy | 831 | 456 |
| Grype | 799 | 433 |

Most of that drop is a fresher base image (newer point-release packages across the board), not the two CVE fixes I made.
> [!NOTE]
> scanners don't shrink their count for a backport by themselves, the way they do for a real version bump.

[`vex/nginx-cve-2026-15176.openvex.json`](vex/nginx-cve-2026-15176.openvex.json) declares the CVE **fixed**, citing the upstream commit backported.
Therefore, we can see `CVE-2026-15176` **is** present in the raw Grype rescan and **absent** once the VEX document is applied (the suppression actually works, not just in theory).

## How I verified the CVE-2026-15176 fix actually works

Applying cleanly and matching a verified upstream commit proves the *patch* is correct, but not that it closes the hole.
I wanted to make sure it works, so I reproduced the exact [config](test/config/cve_2026_15176.conf) from the upstream fix commit's own message, against both images:

**The config:**
```nginx
server {
    listen 80;
    server_name cve-repro;
    location /foo/ {
        alias /bar-target-dir/;
        rewrite ^/foo/.*$ /x;
        return 200 "request_filename=$request_filename\n";
    }
}
```
**The request:**
`GET /foo/1` with `Host: cve-repro`:

**The response:**
- **Baseline:** HTTP 200, `$request_filename` comes back as 11 **null bytes** followed by `/x` (corrupted/uninitialized pool memory sent to the client), not a correct path. No alert logged.
- **Patched:** HTTP 200 with an *empty* `$request_filename`, and the error log shows
  `[alert] "alias" cannot be used in location "/foo/" where URI was rewritten` (the backport's
  new check rejects the mapping before the unsafe arithmetic runs).

I created an automated regression [test](test/cve_2026_15176_test.py) for this exact case.

## Residual risk assessment
It's important to mention that this image still contains CVEs.
I only handled 2 CVEs out of hundreds found in this image. This is due to the scope and the time frame of this assignment. 

**Why there are still risks in this image:**
* The current version of `OpenSSL` is `3.0.22`. This handles CVE-2024-6119, but later OpenSSL vulnerabilities are still present. 
* The patched image uses `nginx` version `1.25.5` with the patch I added for `CVE-2026-15176`, meaning other CVEs that are present in this version are still active. 
* Most packages stayed untouched and so the CVEs they contain stay in the patched image.

**The next thing I'd do:**
* Add the PCRE2 bump (cheap, same mechanism as OpenSSL)
* Look at `CVE-2026-42533` (nginx's `map` directive/script-engine heap overflow), as this was the most severe nginx CVE I found during my research. The patch for this CVE is more complex (its fix is two verified upstream commits) so in the given time frame I deliberately didn't attempt it.


## Insights
This assignment was very interesting for me, as it exposed me to topics and ideas that I was unfamiliar with.
Although it wasn't my "comfort zone" I learned a lot by doing this assignment, including getting to know some of the problem domain echo is facing.

**Anything that surprised me:**
* Severity ratings differ between different sources. Grype calls CVE-2026-15176 Critical, nginx's own advisory calls it Medium. Both are real, they're just scoring it differently.

* Trivy didn't flag `nginx` at all for this image. After some research I discovered it tracks Debian's own `nginx` package (1.22.1), which is a completely different thing from the nginx.org package I actually installed (1.25.5). On the other hand, Grype did manage to catch the real CVEs. Luckily I had 2 scanning tools to compare to one another.

* Apparently hardcoded apt pins go stale fast, not just eventually. I pinned OpenSSL to an exact version and it stopped resolving within this same project. Debian's security mirror only keeps the current point release around, not the one you pinned last week.

**What I'd do differently with more time:** 
I'd probably point the OpenSSL pin at snapshot.debian.org instead of the live mirror so it can't go stale again. I'd also try and patch `CVE-2026-42533`, as it was the most severe nginx CVE I found, which I didn't attempt given the time budget. Looking back at it now, it might not be as complex as I expected it to be. Last thing I'd do is add more test cases to the compatibility test, so it would cover more edge cases.

## AI usage

I used Claude Code for this assignment, especially for planning and initial implementations. It helped me research the CVEs and find the best fit CVEs for this assignment.

Its downfall was in making CVE selection itself. It started hallucinating and got lost. Instead, I changed my approach and let it research specific CVEs that looked like good candidates to me. Then I made a choice based on its research results. Another issue was in planning, it originally ignored some of the instructions stated in the assignment so I had to correct it or fix its output.

As always, AI makes mistakes so I had to debug and correct it from time to time :)