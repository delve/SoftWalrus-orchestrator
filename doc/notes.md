# ToDo
* Reviewer is NOT following the output script, it's making shit up. Is this prompt instruction that needs to move to definition?
* update developer to not leave review references in code comments
* ensure developer and code reviewer are collaborating effectively
* update code reviewer to ONLY produce the findings report. it is currently EXTREMELY verbose for no reason or value

* separate handoff files from long term documentation
* * JSON output files are handoffs. `architecture.md` and `design.md` are long term documentation
* * handoff files should not be versioned. move under `.orchestration/`?
* Consider having review spawn a new developer for each finding for better focus, more similar to a human team too
* remove the interrupt after review, make it contingent on round count (tunable)
* fix the makefile

# Notes
Current testing prompt
`softwalrus run --request "In the Log Food flow move the quick select button for 100% to the beginning of the list, and let the list wrap instead of scrolling."`

# Things to build
* A realtime Claude usage/session display for Ubuntu, so I don't have to set manual timers or check the page all the time
* * desktop display
* * android app with alerts
* * Store API keys locally? Use existing claude auth?

* Reimplement TabsOutliner in my own repo for control, bug fixing, and personal corpo use

* Reimplement Beyondpod. Because it sucks it was removed and everything else is SHITE.