# netops-agent

A Python agent that answers network operations questions ("which switch ports flapped today?", "which SSIDs have the most clients?") by calling the Cisco Meraki Dashboard API on the DevNet always-on sandbox. The tools are exposed through a tool server so other agents can call them.

Evaluated on 30 questions whose ground truth comes from raw API calls.

Status: in progress. See [LOG.md](LOG.md) for each step, measurements, and issues.
