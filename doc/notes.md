# ToDo
* document contract.
* separate handoff files from long term documentation EG Code review & dev notes are handoffs. `architecture.md` and `design.md` are long term documentation
* * Move long term documentation into `docs/`
* * JSON files are orchstration only and should not be versioned, move to `.orchestration/`
* * handoff files should not be versioned. move to `agent_handoffs/` for clarity and add folder to gitignore
* remove the interrupt after review, make it contingent on round count (tunable)
* fix the makefile
* parameterize so many things. agent names, how prompts are built from slash commands, graph flow, regression and round count limits

## longer term thoughts
* Consider having review spawn a new developer for each finding for better focus, more similar to a human team too

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