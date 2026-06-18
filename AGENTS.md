Every Agent launched from this directory must populate memory.md to keep track of tasks long term across sessions. 

# memory.md

Format that should be followed: 
```
# $AGENT_NAME Update at Time: $DD:MM:YYYY:HH:MM:SS.SSS 
1. Decision taken or work performed in a single line
2. Related file or artifact location
3. Reasoning
4. Summary in 3 lines
```

The file has to serve as a long term store of information sharing betweeen agents and should be used as a central reference not a detailed account of everything. 
The file should allow the agent to know enough to access more detailed information. 
An entry should be made in the file whenever a significant change has been made by an agent. 

# Supabase

In the tenexity org, the software-factory-as-a-skill project is what you're supposed to use for the postgres database in software-factory-as-a-skill.

Do not create any new projects on Supabase.

# Architecture

`docs/ARCHITECTURE.md` is the canonical description of how the system is built. Update it on every
major structural change — new/removed service, datastore or schema change, a new pipeline stage or
runtime, an auth/ownership change, or anything that moves where state lives. Keep it aligned with the
diagrams in `docs/`: `docs/schema-erd.svg` is the source-of-truth ERD (schema detail in
`docs/schema-erd.md`), and `docs/service-architecture.svg` is the service/storage topology. Fixing
the doc and diagrams is part of the change that broke them, not a follow-up.

# G Brain
Update gbrain after a significant chunk of work has been completed. 