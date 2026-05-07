# AnoSys CVS Mapping - Single Source of Truth

This document defines the mapping between telemetry attributes and AnoSys Custom Variable (CVS/CVN/CVB) columns. All SDK packages (OpenAI, Agentic, etc.) must adhere to this mapping to ensure dashboard consistency.

---

## 1. Core Conversation & Error (Cluster 1)
| Variable | Internal Name | Description |
| :--- | :--- | :--- |
| **`cvs1`** | **Input** | Main input text, messages list, or prompt. |
| **`cvs2`** | **Output** | Main response text, tool result, or completion. |
| **`cvs3`** | **Error Summary** | Summary error message or failure reason. |
| **`cvs4`** | **Caller** | The name of the calling function, class, or module. |
| **`cvs5`** | **User Context** | JSON blob containing session, user, and context metadata. |
| **`cvs6-9`** | **(Reserved)** | Reserved for future core conversation metadata. |
| **`cvs10`** | **Error Type** | The specific exception/error class name. |
| **`cvs11`** | **Error Message** | The detailed error message. |
| **`cvs12`** | **Error Stack** | Full stack trace for debugging. |

---

## 2. Agentic AI & Advanced Fields (Cluster 2)
Used primarily by `anosys-sdk-openai-agents` and specialized tool traces.

| Variable | Name | Description |
| :--- | :--- | :--- |
| **`cvs60`** | **Object Type** | Record type (e.g., `trace`, `trace.span`). |
| **`cvs61`** | **Event Source** | Lifecycle hook (e.g., `on_trace_start`, `on_span_end`). |
| **`cvs62`** | **Handoffs** | List of agents available for handoff (comma-separated). |
| **`cvs63`** | **Tools** | List of tools available to the agent (comma-separated). |
| **`cvs64`** | **Output Type** | The technical type of the output (e.g., `str`, `json`). |
| **`cvs65`** | **Step Input** | Specialized input for this specific agentic step (also maps to `cvs1`). |
| **`cvs66`** | **Step Output** | Specialized output for this specific agentic step (also maps to `cvs2`). |
| **`cvs67`** | **MCP Data** | Model Context Protocol metadata. |
| **`cvs68`** | **Triggered** | Boolean/String indicating if a guardrail was triggered. |
| **`cvs69`** | **Model** | Specific model name used (e.g., `gpt-4o-mini`). |
| **`cvs70`** | **Model Config** | JSON string of temperature, top_p, and other parameters. |
| **`cvs71`** | **Usage Info** | Summary of token usage for a specific generation. |
| **`cvs72`** | **Custom Data** | Raw data for custom spans or transcription inputs. |
| **`cvs73`** | **Format** | Media/Data format (e.g., `wav`, `mp3`, `markdown`). |
| **`cvs74`** | **Latency Marker**| Time to first content/token (TTS/STT specific). |
| **`cvs75`** | **MCP Server** | Name of the MCP server involved. |
| **`cvs76`** | **MCP Result** | Result code or data from an MCP tool list. |
| **`cvs77`** | **Response ID** | External ID provided by the LLM provider. |
| **`cvs78`** | **From Agent** | Source agent name during a handoff. |
| **`cvs79`** | **To Agent** | Destination agent name during a handoff. |
| **`cvs80`** | **Workflow** | Overall name of the agentic workflow/task. |
| **`cvs81`** | **Group ID** | Organizational or group identifier for the trace. |

---

## 3. Metadata & Technical Fields (Cluster 3)
| Variable | Name | Description |
| :--- | :--- | :--- |
| **`cvs199`** | **Raw JSON** | The complete raw payload for deep inspection. |
| **`cvs200`** | **Trace Source** | Tag identifying the source SDK (`openAI_Traces`, `openAI_Agents_Traces`, etc.). |
| **`cvn1`** | **Start Time** | Start timestamp in numeric milliseconds. |
| **`cvn2`** | **End Time** | End timestamp in numeric milliseconds. |
| **`cvb2`** | **Is Streaming** | Boolean flag indicating if the response was a stream. |

---

## 4. Auto-Assignment Logic
Attributes not explicitly mapped above are assigned sequentially to the first available index in their type category:
- **String Attributes**: Start at `cvs100`
- **Number Attributes**: Start at `cvn3`
- **Boolean Attributes**: Start at `cvb1` (excluding `cvb2`)
