#### **1. User Interaction:**

* **User Sends a Prompt**:

  * The user submits a prompt (text only, or with up to 5 images).
  * **Store User Prompt**: The prompt is stored in the database (in the `chat_messages` table).

#### **2. Image Handling**:

* **If User Attaches Images**:

  * Process the attached images via the image analysis API.
  * **Store Image Descriptions**: The image descriptions are stored in the `image_analysis` table.
  * **Store Images**: The images themselves are stored in the `message_attachments` table (along with their metadata).
  * **Append Image Descriptions**: The image descriptions are appended to the user prompt for embedding generation.

#### **3. Embedding Generation**:

* **Generate Embeddings**:

  * The user’s prompt (with appended image descriptions, if any) is used to generate embeddings using a model.

#### **4. Embedding Comparison**:

* **Retrieve Top N Relevant Chunks**:

  * The generated prompt embedding is compared to the embeddings stored in the database (in `knowledge_chunks`).
  * **Use GIN Indexing** for efficient similarity search (using `pgvector` in PostgreSQL).
  * **Retrieve Top 10 Chunks**: The **top 10 most similar chunks** are retrieved (as per Open Decision #1).

#### **5. Context Management**:

* **Context Window Management**:

  * For the first 5 prompts, send the entire prompt-response history (all previous prompts and responses) to the LLM.
  * After Prompt 5, create an **incremental summary** of previous prompts (based on Open Decision #2, 5 prompt history) and only append summaries for subsequent interactions.
  * **Pass Raw Chunks**: For each prompt, pass the raw content of the last 5 prompts and responses (as-is) along with the **context summary**.

#### **6. Final LLM Call (Single Call)**:

* **Data to Pass to LLM**:

  * **User Prompt**: The original user prompt (without image descriptions, as they are passed separately).
  * **Top 10 Chunks**: The raw content of the 10 most relevant chunks retrieved from the database.
  * **Context Summary**: The summary of previous interactions (from the context window).
  * **Attached Images**: The actual images attached to the prompt (passed as-is).
* **Final LLM Call**:

  * The LLM processes all the data (raw chunks, context summary, and images) to generate a **structured response**.
  * **Return Structured Response**: The LLM's structured response is returned to the frontend for display and stored in the database.

#### **7. Storing Responses**:

* **Store LLM Response**:

  * The generated response from the LLM is stored in the `chat_messages` table in the database for future context.

#### **8. Updating Context Summary**:

* For each new prompt, generate and store the updated **context summary** in the database. This summary will be appended incrementally as the conversation progresses.

---

### **Helper Functions Breakdown**

To implement this pipeline, we need to build a series of **helper functions** that will be called in sequence. Below is a structured outline of the helper functions, listed in the order in which they will be invoked:

---

#### **1. `process_images(prompt, images)`**

* **Purpose**: Process the images attached to the user's prompt.
* **Steps**:

  * Analyze each image via the image analysis API.
  * Store the images and their metadata in the `message_attachments` table.
  * Store the image descriptions in the `image_analysis` table.
  * Append the image descriptions to the original user prompt.

**Input**:

* `prompt`: The user’s original prompt text.
* `images`: List of images attached by the user.

**Output**:

* Updated `prompt` with image descriptions appended.

---

#### **2. `generate_embeddings(text)`**

* **Purpose**: Generate embeddings for the user prompt (including image descriptions).
* **Steps**:

  * Use a model (e.g., Sentence-BERT, OpenAI embeddings, etc.) to generate the embeddings for the provided text.

**Input**:

* `text`: The user prompt, potentially including appended image descriptions.

**Output**:

* `embedding`: The generated embedding for the provided text.

---

#### **3. `retrieve_relevant_chunks(query_embedding, max_results=10)`**

* **Purpose**: Retrieve the top N relevant chunks from the database using the generated query embedding.
* **Steps**:

  * Perform a similarity search using the generated query embedding.
  * Use the **pgvector extension** in PostgreSQL to compare the query embedding with stored embeddings.
  * Retrieve the top N most similar chunks.

**Input**:

* `query_embedding`: The embedding of the user’s prompt.
* `max_results`: The maximum number of chunks to retrieve (default is 10).

**Output**:

* List of top N chunks (with their content and metadata).

---

#### **4. `generate_context_summary(prompts_and_responses)`**

* **Purpose**: Generate a summary of previous prompts and responses.
* **Steps**:

  * Take the last 5 prompts and responses (or fewer if the conversation is short) and generate a concise summary using an LLM or an external summarization model.

**Input**:

* `prompts_and_responses`: List of prompt-response pairs from the current context (e.g., last 5 interactions).

**Output**:

* `context_summary`: A concise summary of the provided prompts and responses.

---

#### **5. `final_llm_call(user_prompt, context_summary, relevant_chunks, images)`**

* **Purpose**: Make the final LLM call to generate a structured response.
* **Steps**:

  * Construct the input for the LLM, combining the user prompt (without image descriptions), relevant chunks (raw content), the context summary, and the attached images.
  * Call the LLM API to generate the final response.
  * Pass the fallback logic in the **system prompt** (as discussed earlier) to allow the LLM to decide when to use its own knowledge.

**Input**:

* `user_prompt`: The user’s original prompt (without image descriptions).
* `context_summary`: The generated summary of the previous prompts and responses.
* `relevant_chunks`: The raw content of the top N relevant chunks.
* `images`: The actual images attached to the prompt.

**Output**:

* `response`: The structured response generated by the LLM.

---

#### **6. `store_response(response_data)`**

* **Purpose**: Store the final response generated by the LLM.
* **Steps**:

  * Store the LLM's generated response in the `chat_messages` table (or wherever appropriate).

**Input**:

* `response_data`: The response content generated by the LLM.

**Output**:

* None (the response is stored in the database).

---

#### **7. `update_context_summary(new_summary)`**

* **Purpose**: Incrementally update the context summary.
* **Steps**:

  * Append the new summary to the existing context summary in the database.

**Input**:

* `new_summary`: The newly generated summary of the latest interaction.

**Output**:

* None (the context summary is updated in the database).

---

### **Final API Workflow**

Here’s the sequence in which these functions will be called in the main API:

1. **process_images(prompt, images)** → Processes any attached images and appends their descriptions to the prompt.
2. **generate_embeddings(text)** → Generates embeddings for the user prompt (with image descriptions).
3. **retrieve_relevant_chunks(query_embedding, max_results=10)** → Retrieves the top N chunks based on the generated embeddings.
4. **generate_context_summary(prompts_and_responses)** → Generates the context summary for previous interactions.
5. **final_llm_call(user_prompt, context_summary, relevant_chunks, images)** → Makes the final call to the LLM to generate the structured response.
6. **store_response(response_data)** → Stores the LLM's response in the database.
7. **update_context_summary(new_summary)** → Updates the context summary in the database for future interactions.

---

### **Conclusion**

This pipeline and the corresponding helper functions will allow for a modular, scalable, and maintainable implementation of your chatbot’s workflow. By keeping each function focused on a specific task (like image processing, embedding generation, and chunk retrieval), the system remains flexible and easy to modify or optimize in the future.
