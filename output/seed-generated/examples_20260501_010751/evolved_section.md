**Example 1: Simple Task Delegation via Role-Based Communication**

- **Input:** A user asks, "I need a recipe for a dairy-free chocolate cake."

- **Protocol Execution:**
    1. User Input Agent receives the request and classifies it under "Cooking & Diet."
    2. Delegation Rule: This topic is routed to the Food & Nutrition Companion Agent.
    3. Communication Pattern: The Food Agent accesses its recipe database and filters for "dairy-free" and "chocolate cake."
    4. The agent returns a short recipe with a link to a full source.

- **Output/Result (to user):** "Here’s a simple dairy-free chocolate cake recipe: 1 ½ cups flour, 1 cup sugar, ⅓ cup cocoa powder, 1 tsp baking soda, ½ tsp salt, 1 cup water, ⅓ cup vegetable oil, 1 tbsp vinegar, 1 tsp vanilla. Mix dry ingredients, add wet, bake at 350°F for 30 min. Full instructions: [link]"

---

**Example 2: Escalation Path for Out-of-Scope Request**

- **Input:** "Can you check my blood pressure from my wearable and tell me if it’s dangerous?"

- **Protocol Execution:**
    1. Health Monitoring Agent receives request. It detects this involves medical diagnosis.
    2. Escalation Rule: The agent cannot provide medical advice. It follows the escalation path:  
       - Level 1: Inform the user of limitations.  
       - Level 2: If user persists, offer to connect to a human healthcare provider via a secure link.
    3. Communication Pattern: The agent sends a polite refusal and a referral to a telehealth service.

- **Output/Result (to user):** "I cannot interpret blood pressure readings for medical diagnosis. For safety, please consult a healthcare professional. Would you like me to connect you to a telehealth provider?"

---

**Example 3: Multi-Agent Coordination and Conflict Resolution**

- **Input:** "I have a dentist appointment at 3 PM today, but also a project deadline at 5 PM. Help me plan."

- **Protocol Execution:**
    1. Scheduling Agent and Task Management Agent both claim relevance.  
    2. Delegation Rule: A collaborative task is established.  
       - Scheduling Agent handles the dentist appointment (time, location, travel).  
       - Task Management Agent handles the deadline (steps, estimated work time).  
    3. Communication Pattern: Agents negotiate without conflict. The Task Agent calculates 2 hours needed for the project. The Scheduling Agent notes travel time (30 min).  
    4. Combined output.

- **Output/Result (to user):** "Here’s a plan:  
   - Dentist at 3:00 PM (leave home by 2:25 PM).  
   - Return by 3:45 PM.  
   - Work on project from 3:45 PM to 5:45 PM.  
   - Submit by 5:00 PM? You might need to start earlier or adjust. Would you like me to block out time now?"