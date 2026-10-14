# Agente de soporte (LangGraph)

Departamento: **Formación** (Jake Morrison — la misma búsqueda de estándares, con cada decisión visible) y **Dirección** (Mariana Restrepo — una pregunta en lenguaje natural y el rastro de cómo se respondió). La ruta está en la API central de **Tecnología**.

`POST /agent/query` invoca un grafo compilado al importar el módulo. Los nodos llaman a `retrieve` y `generate_answer` en `data/pipelines/rag.py`. No llaman a `query()`, que volvería a recuperar.

| Nodo | Cuándo corre |
| --- | --- |
| `receive_question` | Cada petición. Una pregunta vacía detiene el grafo. |
| `retrieve` | Pregunta no vacía. Llama a `retrieve()`. |
| `query` | Al menos un fragmento superó el umbral. Llama a `generate_answer(question, context)`. |
| `honest_answer` | La recuperación no devolvió contexto por encima del umbral. |

`GET /agent/traces/{trace_id}` devuelve los pasos de esa ejecución. `POST /knowledge/query` no cambia.
