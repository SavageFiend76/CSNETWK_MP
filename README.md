# Build and Run Instructions
1. Open 2 cmd prompts. 
2. Always run the server first. On the first cmd, type the command python -m server.server --verbos to open the server. 
3. This step is for running the player (client). On the other cmd, type the command python -m client.ui to open the client. 

# Work Distribution
1. Greg Avila 
- TCP Server: connection handling, framing, dispatch
- Error handling, PING/PONG heartbeat, disconnect logic
- Combat system (attackers, blockers, damage)
- Priority & Stack logic, spell/ability resolution
2. Joshua Del Mundo
- Testing & interoperability
- README / documentation / AI disclosure
3. Ulrich Gonzales
- Game lifecycle: LOBBY, GAME_SETUP, MULLIGAN logic
- Client implementation & state rendering
- Verbose mode (client + server PDU logging, toggle on/off)
4. Mark Sandoval
- Turn & phase engine (all phases/steps, transitions)
- PDU serialization/deserialization (all 25 PDU types)
  
# AI Declaration 
