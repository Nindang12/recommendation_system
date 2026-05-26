"""
Benchmark: Prompt goc (few-shot) vs Prompt rut gon (no few-shot)
"""
import json, time, urllib.request

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3"
OPTIONS = {"temperature": 0.3, "top_p": 0.9, "top_k": 40, "num_predict": 512}

# --- Lay 1 recommendation tu API ---
api_url = "http://localhost:8000/api/v1/recommendations/policy"
api_data = json.dumps({
    "source_id": "exp_005", "source_type": "expert",
    "target_type": "expert", "limit": 3
}).encode("utf-8")
req = urllib.request.Request(api_url, data=api_data, headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req)
recs = json.loads(resp.read().decode()).get("data", [])
rec = recs[0]
name = rec.get("name", rec.get("id", "Unknown"))
score = rec.get("score", 0.0)

# Lay paths_block tu recommendation
paths = rec.get("reasoning_paths", [])[:3]
paths_lines = []
for i, p in enumerate(paths):
    path_str = p.get("path", "") if isinstance(p.get("path"), str) else str(p.get("path", ""))
    s = p.get("score", 0)
    paths_lines.append(f"{i+1}. {path_str} (do tin cay: {s:.0%})")
paths_block = "\n".join(paths_lines) if paths_lines else "(khong co du lieu)"

# =============================================
# PROMPT GOC (CO FEW-SHOT) ~ 700-1000 token
# =============================================
PROMPT_ORIGINAL = f"""BAN LA: Tro ly AI chuyen nghiep phan tich du lieu cho he thong goi y.

QUY TAC BAT BUOC:
1. Viet 3-5 cau tieng Viet that tu nhien, luu loat, mang tinh tu van chuyen nghiep.
2. TUYET DOI KHONG dung cac tu ngu ky thuat nhu: "duong dan", "node", "edge", "do thi tri thuc", "KG". Thay vao do hay dung: "He thong ghi nhan", "Du lieu cho thay", "Kinh nghiem thuc te", "Mang luoi ket noi".
3. Neu gap cac tu khoa viet hoa dang ky thuat (nhu FOCUSES_ON_SECTORS, PARTICIPATES_IN, HAS_EXPERTISE_IN), hay tu dong dich sang tieng Viet tu nhien.
4. Chi dua vao thong tin co san, KHONG tu bia them chi tiet.
5. Tuyet doi KHONG mo dau bang cac tu nhu "Toi...", "Chung toi...". Hay di thang vao noi dung phan tich.
6. Cau truc ly tuong: [Boi canh] + [Phan tich diem chung] + [Loi ich mang lai].

===== VI DU MAU (expert) =====
Goi y: chuyen gia PGS.TS. Tran Van A cho du an Smart City IoT
Du lieu ket noi:
1. Smart City IoT -> IoT -> PGS.TS. Tran Van A (do tin cay: 65%)
2. Nhom nghien cuu B -> PGS.TS. Tran Van A (do tin cay: 55%)

Output mau:
Du an Smart City IoT dang nham den linh vuc IoT, day cung chinh la mang chuyen mon the manh cua PGS.TS. Tran Van A. Du lieu con cho thay vi chuyen gia nay co moi quan he hop tac mat thiet voi Nhom nghien cuu B, mo ra tiem nang mo rong mang luoi nghien cuu cho du an.

===== NHIEM VU =====
Goi y: chuyen gia **{name}**
Do phu hop: {score:.0%}

Du lieu ket noi:
{paths_block}

Hay phan tich vi sao chuyen gia **{name}** phu hop, tap trung vao nang luc chuyen mon va mang luoi ket noi."""


# =============================================
# PROMPT RUT GON (KHONG CO FEW-SHOT) ~ 200 token
# =============================================
PROMPT_SHORT = f"""Viet 3-5 cau tieng Viet tu nhien, tu van chuyen nghiep.
KHONG dung: "duong dan", "node", "edge", "do thi", "KG".
Dich tu khoa ky thuat viet hoa sang tieng Viet. Chi dung thong tin co san, KHONG bia them. Di thang vao phan tich.

Goi y: chuyen gia **{name}**
Do phu hop: {score:.0%}

Du lieu ket noi:
{paths_block}

Phan tich vi sao chuyen gia **{name}** phu hop, tap trung vao chuyen mon va mang luoi ket noi."""


def call_ollama(prompt):
    body = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": OPTIONS,
    }).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL, data=body,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    start = time.time()
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        elapsed = time.time() - start
        text = (data.get("response") or "").strip()
        return elapsed, text


print("=" * 60)
print(f"Testing with: {name} (score: {score:.0%})")
print(f"Paths count: {len(paths)}")
print("=" * 60)

# Test 1: Prompt goc
print("\n[1/2] PROMPT GOC (co few-shot)...")
print(f"  Input tokens (est): ~{len(PROMPT_ORIGINAL)//4}")
t1, text1 = call_ollama(PROMPT_ORIGINAL)
print(f"  Thoi gian: {t1:.1f} giay")
print(f"  Output: {len(text1)} chars")
print(f"  Preview: {text1[:150]}...")

# Test 2: Prompt rut gon
print("\n[2/2] PROMPT RUT GON (khong few-shot)...")
print(f"  Input tokens (est): ~{len(PROMPT_SHORT)//4}")
t2, text2 = call_ollama(PROMPT_SHORT)
print(f"  Thoi gian: {t2:.1f} giay")
print(f"  Output: {len(text2)} chars")
print(f"  Preview: {text2[:150]}...")

# Summary
print("\n" + "=" * 60)
print("KET QUA SO SANH:")
print(f"  Prompt goc (few-shot):     {t1:.1f}s")
print(f"  Prompt rut gon (no few-shot): {t2:.1f}s")
print(f"  Chenh lech: {t1-t2:.1f}s ({(1-t2/t1)*100:.0f}% nhanh hon)")
print("=" * 60)
