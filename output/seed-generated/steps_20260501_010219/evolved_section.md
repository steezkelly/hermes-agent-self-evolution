1. Extract the role description from the user input or task specification to understand the persona's context.
2. Define the persona's **voice** (e.g., authoritative, empathetic, neutral) based on the role's professional environment.
3. Determine the **tone** (e.g., formal, conversational, instructional) appropriate for the intended audience.
4. Specify the **response style** (e.g., concise bullet points, detailed narratives, step-by-step guides) and any formatting preferences (e.g., markdown, lists).
5. List the **domain expertise** areas the persona should cover, such as "medical informatics" or "cloud infrastructure".
6. Enumerate **behavioral constraints** including prohibited topics, mandatory disclaimers, or required citation formats (e.g., "Always include a source for technical claims").
7. Run `hermes persona create --name <persona_name>` to initialize a new persona profile.
8. Edit the generated YAML configuration (or use `hermes persona edit <persona_name>`) to set each field: `voice`, `tone`, `response_style`, `expertise`, and `constraints`.
9. Validate the persona by executing `hermes interact --persona <persona_name> --input "Test prompt"` to verify that responses align with the defined attributes.
10. Repeat steps 8–9 until the output matches the desired characteristics.
11. Finalize the persona and commit the configuration file to version control if required.