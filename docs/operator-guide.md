# Using Gateway care

Open the healer at `http://127.0.0.1:8085/` through the existing SSH tunnel. Choose your private `operator.token` access file; no username is needed. You can paste the same token under the alternative sign-in section. The file is not a password reset or a new account.

## Start here

The top cards answer whether the independent request succeeds, how much permission the healer currently has, and whether the backend responds. **Not known** means readings are missing, stale or unusable; it does not mean healthy. A connection-loss message marks the displayed service cards unavailable. The live health cards continue updating while you type an incident decision.

Under **What needs your attention**, a healthy idle system says **Nothing needs a repair right now**. Current unresolved incidents show a short explanation and the next available decision. The page does not fill this section with closed experiments or incidents for a replaced gateway identity.

## If an incident appears

- A diagnosed port-capacity incident can offer **Approve this temporary repair**. Enter your name and the reason. Only the already qualified namespace repair can execute, and all server/root safety checks still apply.
- An unexplained incident has no repair approval button. Open **Investigate with AI**, enter your name and select **Ask AI for an explanation**. Read the summary first, then expand possible causes, checks or verification as needed. These are suggestions, not confirmed facts or permission to run commands.
- If you repair something through administrator access, open **Record or review a manual repair**. Describe the change and how you checked it. The saved note does not automatically qualify future execution.
- An executing incident reports that verification is in progress. Successful independent requests, not a setting change alone, establish recovery.

## What the other sections mean

**Past incidents** contains the latest ten past outcomes and their saved AI/evidence notes. Older records remain retained in Knowledge/private backups; they have not been deleted. Past AI text describes its submitted evidence, not the current state.

**Automation settings** offers **Watch only**, **Ask before repairing** and **Reuse reviewed repairs**. A name and reason are recorded for mode changes. Automatic mode still requires a matching qualified procedure. Two distinct verified occurrences and explicit operator review qualify reuse; the human repair note and an AI report cannot do this.

**Technical evidence and audit** is for troubleshooting and research. Raw measurements, identities and audit records stay out of the everyday overview but remain available here.

## Monitoring dashboard

The **Monitoring** link opens **Gateway care - service health and recovery** in Grafana. Start with the four status cards. The main charts then show response time, outgoing-port use, new errors in the last minute and available memory. Incident, procedure and rollback history belongs in the healer rather than this service-health dashboard. The four duplicate history/coverage panels have been removed; their measurements and alerts remain collected. A return link opens the healer for operator decisions.

The dashboard presents existing measurements; it does not add a new fault detector or change the repair catalogue. Prometheus scraping, alert rules, approval controls, audit retention and authentication are unchanged.
