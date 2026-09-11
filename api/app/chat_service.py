import re
import logging
from typing import Dict, Any, List, Optional
from app.neo4j_service import neo4j_service

logger = logging.getLogger(__name__)

FORBIDDEN_CYPHER_KEYWORDS = [
    r'\bCREATE\b', r'\bMERGE\b', r'\bDELETE\b', r'\bDETACH\b', r'\bSET\b',
    r'\bREMOVE\b', r'\bDROP\b', r'\bCALL\s+dbms\b', r'\bLOAD\s+CSV\b', r'\bFOREACH\b'
]

STOPWORDS = set([
    "give", "me", "the", "them", "from", "with", "what", "where", "show", "find", 
    "list", "rows", "records", "data", "file", "csv", "info", "that", "this", 
    "customers", "customer", "all", "are", "get", "there", "have", "has", "does",
    "is", "in", "of", "to", "for", "a", "an", "some", "how", "many", "count",
    "equal", "equals", "by", "per", "and", "or", "which", "tell", "display", "retrieve",
    "details", "about", "who"
])

PREFIX_STOPWORDS = [
    "what is ", "what are ", "tell me about ", "tell me ", "show me ", "give me ",
    "get ", "find ", "where is ", "who is ", "details of ", "details for ", "is "
]

def clean_entity_name(raw: str) -> str:
    cleaned = raw.strip()
    cleaned_lower = cleaned.lower()
    for prefix in PREFIX_STOPWORDS:
        if cleaned_lower.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            cleaned_lower = cleaned.lower()
    return cleaned

class ChatService:
    def is_cypher_safe(self, cypher: str) -> bool:
        if not cypher:
            return False
        upper_cypher = cypher.upper()
        for kw in FORBIDDEN_CYPHER_KEYWORDS:
            if re.search(kw, upper_cypher, re.IGNORECASE):
                return False
        return True

    def process_question(self, question: str) -> Dict[str, Any]:
        q = question.strip()
        if not q:
            return {
                "answer": "Please provide a question about the uploaded dataset.",
                "cypher": None,
                "result": [],
                "grounded": False
            }

        # Fetch schema columns stored in Neo4j
        available_cols = set()
        try:
            sample_res = neo4j_service.execute_read_query("MATCH (r:Row) RETURN keys(r) AS k LIMIT 5")
            for row in sample_res:
                keys_list = row.get("k", []) or (row.get("columns", []) if isinstance(row.get("columns"), list) else [])
                for k in keys_list:
                    if k not in ("dataset_id", "row_index"):
                        available_cols.add(k)
        except Exception as e:
            logger.warning(f"Schema inspection warning: {e}")

        # Check if dataset is loaded
        latest = neo4j_service.get_latest_dataset()
        if not latest or latest.get("row_count", 0) == 0:
            if not available_cols:
                return {
                    "answer": "No dataset has been loaded yet. Please upload a CSV dataset first.",
                    "cypher": None,
                    "result": [],
                    "grounded": False
                }

        # Execute Intent & Intelligent Value Matching
        result = self.match_intent_and_execute(q, available_cols)
        if result:
            return result

        # Fallback for unsupported or missing column questions
        col_str = ", ".join(sorted(list(available_cols))) if available_cols else "none"
        return {
            "answer": f"I don't have that information in the uploaded dataset. Available columns: {col_str}.",
            "cypher": None,
            "result": [],
            "grounded": False
        }

    def find_best_column_match(self, phrase: str, cols: set) -> Optional[str]:
        if not phrase:
            return None
        phrase_clean = phrase.strip().lower().replace("_", " ")
        # 1. Exact match
        for c in cols:
            if c.lower().replace("_", " ") == phrase_clean:
                return c
        # 2. Substring match
        for c in cols:
            c_norm = c.lower().replace("_", " ")
            if c_norm in phrase_clean or phrase_clean in c_norm:
                return c
        return None

    def match_intent_and_execute(self, q: str, cols: set) -> Optional[Dict[str, Any]]:
        q_lower = q.lower()

        # Explicit unsupported attributes check
        for test_field in ["blood group", "blood_group", "ssn", "passport", "salary_tax", "weather", "zipcode"]:
            if test_field in q_lower and not any(test_field in c.lower() for c in cols):
                return {
                    "answer": f"I don't have information about '{test_field}' in the uploaded data.",
                    "cypher": None,
                    "result": [],
                    "grounded": False
                }

        # 1. ENTITY + ATTRIBUTE LOOKUP STATEMENTS
        # Examples: "what is Arun's order_amount", "give me the city of Ravi Kumar", "salary of Arun Raj"
        cand_attr, raw_entity = None, None

        # Pattern A: "the <attr> of/for <entity>" or "what is <attr> for <entity>"
        m_of = re.search(r'(?:the\s+)?([a-zA-Z0-9_\s]+)\s+(?:of|for|belonging to|about)\s+([a-zA-Z0-9_\s]+)', q_lower)
        if m_of:
            cand_attr = m_of.group(1).strip()
            raw_entity = m_of.group(2).strip()

        # Pattern B: "<entity>'s <attr>"
        m_possessive = re.search(r'([a-zA-Z0-9_\s]+)\'?s\s+([a-zA-Z0-9_\s]+)', q_lower)
        if m_possessive and not cand_attr:
            raw_entity = m_possessive.group(1).strip()
            cand_attr = m_possessive.group(2).strip()

        if cand_attr and raw_entity:
            entity_query = clean_entity_name(raw_entity)
            cand_attr = re.sub(r'[\?\.\!]', '', cand_attr).strip()
            entity_query = re.sub(r'[\?\.\!]', '', entity_query).strip()

            if cand_attr and entity_query and cand_attr not in ("how", "many", "rows", "records", "count", "show", "first"):
                target_attr = self.find_best_column_match(cand_attr, cols)
                cypher_entity_search = f"MATCH (r:Row) WHERE any(key in keys(r) WHERE key NOT IN ['dataset_id', 'row_index'] AND toLower(toString(r[key])) CONTAINS toLower('{entity_query}')) RETURN properties(r) AS row LIMIT 5"
                res = neo4j_service.execute_read_query(cypher_entity_search)

                if res:
                    r_obj = res[0].get("row", res[0].get("r", res[0]))
                    if isinstance(r_obj, dict):
                        entity_name = r_obj.get("customer_name") or r_obj.get("Name") or r_obj.get("customer_id") or entity_query.title()
                        if target_attr and target_attr in r_obj:
                            attr_val = r_obj.get(target_attr)
                            return {
                                "answer": f"The {target_attr} for {entity_name} is {attr_val}.",
                                "cypher": cypher_entity_search,
                                "result": [r_obj],
                                "grounded": True
                            }
                        else:
                            # Entity found, but requested attribute is not in columns!
                            col_str = ", ".join(sorted(list(cols)))
                            return {
                                "answer": f"I found '{entity_name}' in the dataset, but column '{cand_attr}' is not present. Available columns: {col_str}.",
                                "cypher": None,
                                "result": [r_obj],
                                "grounded": False
                            }

        # 2. Explicit Equals/Filter Matcher: e.g. "how many rows have group = Billing", "show rows where city = Chennai"
        eq_match = re.search(r'\b([a-zA-Z0-9_]+)\s*(=|is|equal to|equals)\s*[\'"]?([a-zA-Z0-9_\s]+)[\'"]?', q_lower)
        if eq_match:
            candidate_col = eq_match.group(1).strip()
            val = eq_match.group(3).strip()
            target_col = self.find_best_column_match(candidate_col, cols)
            if target_col:
                is_count = "how many" in q_lower or "count" in q_lower
                if is_count:
                    cypher = f"MATCH (r:Row) WHERE toLower(toString(r.`{target_col}`)) = toLower('{val}') RETURN count(r) AS count"
                    res = neo4j_service.execute_read_query(cypher, {"val": val})
                    cnt = res[0].get("count", 0) if res else 0
                    return {
                        "answer": f"There are {cnt} rows where {target_col} is {val.title()}.",
                        "cypher": cypher,
                        "result": res,
                        "grounded": True
                    }
                else:
                    cypher = f"MATCH (r:Row) WHERE toLower(toString(r.`{target_col}`)) = toLower('{val}') RETURN properties(r) AS row LIMIT 10"
                    res = neo4j_service.execute_read_query(cypher, {"val": val})
                    clean_res = []
                    names = []
                    for item in res:
                        r_obj = item.get("row") or item.get("r") or item
                        if isinstance(r_obj, dict):
                            clean = {k: v for k, v in r_obj.items() if k not in ("dataset_id", "row_index")}
                            clean_res.append(clean)
                            name = clean.get("customer_name") or clean.get("Name") or clean.get("customer_id")
                            if name:
                                names.append(str(name))

                    statement_names = ", ".join(names[:5]) if names else f"{len(clean_res)} records"
                    return {
                        "answer": f"The records where {target_col} is {val.title()} are: {statement_names}.",
                        "cypher": cypher,
                        "result": clean_res,
                        "grounded": True
                    }

        # 3. Total Row Count
        if re.search(r'\b(how many rows|total rows|row count|number of rows|count of rows|how many records|total records)\b', q_lower) and not re.search(r'\b(where|have|with|=|is|from|in)\b', q_lower):
            cypher = "MATCH (r:Row) RETURN count(r) AS total_rows"
            res = neo4j_service.execute_read_query(cypher)
            count = res[0].get("total_rows", res[0].get("count(r)", 0)) if res else 0
            return {
                "answer": f"There are {count} total rows in the dataset.",
                "cypher": cypher,
                "result": res,
                "grounded": True
            }

        # 4. Available Columns
        if re.search(r'\b(what columns|available columns|list columns|show columns|column names|headers|fields)\b', q_lower):
            col_list = sorted(list(cols))
            cypher = "MATCH (r:Row) RETURN keys(r) AS columns LIMIT 1"
            return {
                "answer": f"The available dataset columns are: {', '.join(col_list)}.",
                "cypher": cypher,
                "result": [{"columns": col_list}],
                "grounded": True
            }

        # 5. Show First N Rows
        first_n_match = re.search(r'\b(show|display|get|view|list)\s+(the\s+)?first\s+(\d+)\s+rows\b', q_lower)
        if first_n_match or "first 5 rows" in q_lower or "first 10 rows" in q_lower:
            n = int(first_n_match.group(3)) if first_n_match else (10 if "first 10" in q_lower else 5)
            cypher = f"MATCH (r:Row) RETURN properties(r) AS row LIMIT {n}"
            res = neo4j_service.execute_read_query(cypher)
            clean_res = []
            for item in res:
                r_obj = item.get("row") or item.get("r") or item
                if isinstance(r_obj, dict):
                    clean = {k: v for k, v in r_obj.items() if k not in ("dataset_id", "row_index")}
                    clean_res.append(clean)
            return {
                "answer": f"Displaying the first {len(clean_res)} records from the dataset.",
                "cypher": cypher,
                "result": clean_res,
                "grounded": True
            }

        # 6. Average <column>
        avg_match = re.search(r'\b(average|avg|mean)\s+(of\s+)?([a-zA-Z0-9_\s]+)\b', q_lower)
        if avg_match:
            candidate = avg_match.group(3).strip()
            target_col = self.find_best_column_match(candidate, cols)
            if target_col:
                cypher = f"MATCH (r:Row) WHERE r.`{target_col}` IS NOT NULL RETURN avg(toInteger(r.`{target_col}`)) AS avg_value"
                res = neo4j_service.execute_read_query(cypher)
                avg_val = res[0].get("avg_value") if res else None
                if avg_val is not None:
                    return {
                        "answer": f"The average {target_col} across all records is {round(float(avg_val), 2)}.",
                        "cypher": cypher,
                        "result": res,
                        "grounded": True
                    }

        # 7. Max / Min <column>
        max_min_match = re.search(r'\b(maximum|max|highest|minimum|min|lowest)\s+(value\s+of\s+)?([a-zA-Z0-9_\s]+)\b', q_lower)
        if max_min_match:
            op = max_min_match.group(1)
            candidate = max_min_match.group(3).strip()
            target_col = self.find_best_column_match(candidate, cols)
            if target_col:
                func = "max" if op in ("maximum", "max", "highest") else "min"
                cypher = f"MATCH (r:Row) WHERE r.`{target_col}` IS NOT NULL RETURN {func}(toInteger(r.`{target_col}`)) AS val"
                res = neo4j_service.execute_read_query(cypher)
                val = res[0].get("val") if res else None
                if val is not None:
                    return {
                        "answer": f"The {func} {target_col} in the dataset is {val}.",
                        "cypher": cypher,
                        "result": res,
                        "grounded": True
                    }

        # 8. Column + Value Natural Language Matcher (e.g. "give me the customers from the city Chennai")
        tokens = [t.strip() for t in re.findall(r'\b[a-zA-Z0-9_]+\b', q_lower)]
        non_stopwords = [t for t in tokens if t not in STOPWORDS]

        matched_col = None
        for col in cols:
            if col.lower() in q_lower:
                matched_col = col
                break

        value_cand = None
        for t in non_stopwords:
            if matched_col and t.lower() == matched_col.lower():
                continue
            value_cand = t
            break

        if matched_col and value_cand:
            is_count = "how many" in q_lower or "count" in q_lower
            if is_count:
                cypher = f"MATCH (r:Row) WHERE toLower(toString(r.`{matched_col}`)) = toLower('{value_cand}') RETURN count(r) AS count"
                res = neo4j_service.execute_read_query(cypher, {"val": value_cand})
                cnt = res[0].get("count", 0) if res else 0
                return {
                    "answer": f"There are {cnt} records where {matched_col} is {value_cand.title()}.",
                    "cypher": cypher,
                    "result": res,
                    "grounded": True
                }
            else:
                cypher = f"MATCH (r:Row) WHERE toLower(toString(r.`{matched_col}`)) = toLower('{value_cand}') RETURN properties(r) AS row LIMIT 10"
                res = neo4j_service.execute_read_query(cypher, {"val": value_cand})
                clean_res = []
                names = []
                for item in res:
                    r_obj = item.get("row") or item.get("r") or item
                    if isinstance(r_obj, dict):
                        clean = {k: v for k, v in r_obj.items() if k not in ("dataset_id", "row_index")}
                        clean_res.append(clean)
                        name = clean.get("customer_name") or clean.get("Name") or clean.get("customer_id")
                        if name:
                            names.append(str(name))
                if clean_res:
                    statement_names = ", ".join(names[:5]) if names else f"{len(clean_res)} records"
                    return {
                        "answer": f"The records for {matched_col} '{value_cand.title()}' are: {statement_names}.",
                        "cypher": cypher,
                        "result": clean_res,
                        "grounded": True
                    }

        # 9. UNIVERSAL GRAPH VALUE SEARCH FALLBACK (Substrings via CONTAINS)
        for word in non_stopwords:
            if len(word) < 3:
                continue
            cypher = f"MATCH (r:Row) WHERE any(key in keys(r) WHERE key NOT IN ['dataset_id', 'row_index'] AND toLower(toString(r[key])) CONTAINS '{word}') RETURN properties(r) AS row LIMIT 10"
            res = neo4j_service.execute_read_query(cypher)
            if res:
                clean_res = []
                names = []
                for item in res:
                    r_obj = item.get("row") or item.get("r") or item
                    if isinstance(r_obj, dict):
                        clean = {k: v for k, v in r_obj.items() if k not in ("dataset_id", "row_index")}
                        clean_res.append(clean)
                        name = clean.get("customer_name") or clean.get("Name") or clean.get("customer_id")
                        if name:
                            names.append(str(name))

                statement_names = ", ".join(names[:5]) if names else f"{len(clean_res)} records"
                return {
                    "answer": f"Found matching records for '{word.title()}': {statement_names}.",
                    "cypher": cypher,
                    "result": clean_res,
                    "grounded": True
                }

        return None

chat_service = ChatService()

