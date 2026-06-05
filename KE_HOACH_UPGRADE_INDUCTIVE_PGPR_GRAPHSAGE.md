# Ke hoach nghien cuu Inductive PGPR candidate voi GraphSAGE end-to-end

Ngay tao: 2026-06-05  
Trang thai: research/candidate, khong thay the PGPR/hybrid production hien tai neu chua qua evaluation gate.

## 1. Muc tieu

Muc tieu cua ke hoach nay la nghien cuu mot **Inductive PGPR candidate**: policy reasoning co the dung GraphSAGE encoder de sinh embedding dong cho node moi, thay vi phu thuoc hoan toan vao `vocab.json` va embedding lookup co dinh.

Trang thai hien tai:

- PGPR classic dung `vocab.json`, `entity_emb.npy`, `relation_emb.npy`, `policy.pt`.
- Node moi khong co trong `vocab.json` thi PGPR classic khong rollout truc tiep duoc.
- GraphSAGE-lite hien la cold-start bridge: tao embedding, tim candidate, hybrid rerank.
- Hybrid hien tai van la baseline van hanh an toan.

Muc tieu candidate:

- Encode node moi bang GraphSAGE dua tren feature va neighborhood.
- Tao state/action embedding dong cho policy.
- Chay rollout tren graph runtime/snapshot ma khong bat buoc source node co trong vocab train cu.
- Giu duoc reasoning path va XAI neu path hop le.

Khong mac dinh thay the PGPR hien tai. Candidate chi duoc promote neu vuot baseline hybrid qua evaluation/regression gate.

## 2. Y tuong kien truc

Kien truc hien tai:

```text
source node
-> kiem tra vocab.json
-> neu co: PGPR classic rollout
-> neu khong: Cypher/GraphSAGE hybrid fallback
```

Kien truc Inductive PGPR candidate:

```text
source node runtime
-> GraphSAGE encoder lay node feature + neighborhood
-> tao state embedding dong
-> lay valid actions theo action schema da freeze
-> encode next_node trong moi action bang GraphSAGE/cache
-> policy network score action
-> rollout/beam search tren graph
-> validate path + governance mask
-> tra target + reasoning path + XAI
```

Diem khac biet quan trong:

- `vocab.json` khong con la dieu kien bat buoc de source node duoc rollout.
- Entity embedding khong chi la lookup `.npy`, ma duoc encoder sinh ra.
- Van can relation/action schema de policy biet duoc phep di qua quan he nao.
- Van can governance mask de khong lo private/rejected/disabled node.

## 3. Feasibility Check

### Phase -1 - Feasibility Check

Truoc khi train that, can kiem tra kha thi:

- So node/edge co du lon chua.
- So positive labels co du cho tung task chua.
- Ty le node moi/cold-start trong evaluation co du y nghia khong.
- PyTorch Geometric hoac implementation GraphSAGE thuan PyTorch da san sang chua.
- Dung luong graph, latency encode, latency rollout co chap nhan duoc khong.
- Neu data qua it, chi lam simulator/prototype va report `promote_allowed=false`, khong train/promote that.

Nguong goi y ban dau:

- Node: toi thieu vai nghin node neu ky vong deep model vuot baseline.
- Edge: toi thieu hang chuc nghin edge co y nghia.
- Positive labels: toi thieu vai tram den vai nghin label moi huong chinh.
- Cold-start eval cases: phai co tap case rieng cho node moi.

Voi graph hien tai chi khoang vai tram node/edge, muc tieu hop ly la **lifecycle/prototype**, chua ky vong model deep learning vuot hybrid baseline manh.

## 4. Snapshot, runtime graph va action schema

### Training graph snapshot

Snapshot dung cho train/eval phai:

- Duoc sanitize va versioned.
- Loai/redact secret, email, phone, token, password hash.
- Mask node rejected/disabled/private khong duoc train.
- Loai edge governance/private neu khong phuc vu recommendation.
- Luu metadata: snapshot time, schema version, node counts, edge counts, relation counts.
- Luu label source va split train/val/test reproducible.

### Runtime graph

Runtime graph la Neo4j hien tai, co the thay doi theo user/admin action. Runtime phai:

- Di qua `CandidateMaskService` hoac governance mask tuong duong.
- Khong expose `owner_only` cua user khac.
- Khong di qua node `rejected`, `disabled`, `merge_required`.
- Ton trong `visibility`, `participation_scope`, `recommendable_as_target`, `allow_as_intermediate_node`.

### Relation/action schema freeze

Inductive PGPR phai freeze danh sach relation duoc phep di. Khong cho policy tu do di qua moi relation trong Neo4j.

Vi du ban dau:

```text
ALLOWED_ACTION_RELATIONS = [
  "FOCUSES_ON_TOPIC",
  "HAS_EXPERIENCE_IN",
  "INTERESTED_IN",
  "RESEARCHES",
  "FOCUSES_ON",
  "HAS_SKILL",
  "REQUIRES_SKILL",
  "USES_SKILL",
  "SUPPORTS_SKILL",
  "LOCATED_IN",
  "OPERATES_IN",
  "FOCUSES_ON_SECTORS",
  "FUNDS",
  "PARTNERS_WITH",
  "PARTICIPATES_IN"
]
```

Can dinh nghia them:

- Relation nao duoc di xuoi/nguoc.
- Relation nao chi dung lam evidence, khong duoc lam action.
- Relation nao bi cam vi private/governance/audit.
- Max path length theo tung source/target type.

## 5. Thanh phan can xay dung

### 5.1 GraphSAGE encoder

Input:

- Node type: Expert, Project, Funder, Enterprise, ResearchTopic, Skill, Industry, Location, ...
- Text/hash features: name/title/topic/skill/industry/location.
- Governance features: trust_weight, verification, visibility.
- Neighborhood sampled tu training snapshot hoac runtime graph.

Output:

- Node embedding 128 hoac 256 chieu.
- Metadata: model version, source_hash, graph_schema_version.

Artifact:

- `graphsage_model.pt`
- `node_feature_encoder.pkl`
- `graph_schema.json`
- `model_metadata.json`
- `active_embedding_model.json`

### 5.2 InductiveKGEnv

Tao moi:

```text
backend/pgpr/inductive_pgpr_env.py
```

Trach nhiem:

- Lay action runtime tu Neo4j hoac snapshot cache.
- Ap dung `ALLOWED_ACTION_RELATIONS`.
- Ap dung governance mask.
- Ho tro source node moi.
- Ho tro target type filtering.
- Cache neighbor/action theo node id + graph version.

### 5.3 InductivePolicyNetwork

Policy moi khong lookup entity embedding co dinh:

```text
current_emb = GraphSAGE(current_node)
next_emb = GraphSAGE(next_node)
relation_emb = RelationEmbedding(relation_type)
action_emb = relation_emb + next_emb
score = MLP([state_emb, action_emb, path_context, target_type_emb])
```

Can co:

- Path history embedding.
- Relation history.
- Target type conditioning.
- Action mask.
- Fallback khi node/no-neighbor/no-signal.

### 5.4 Training objective

Co the dung REINFORCE/actor-critic, nhung state/action embedding do GraphSAGE sinh ra.

Positive pairs:

- Project -> Expert: participant/collaboration label.
- Project -> Project: related project/shared topic/direction/funder.
- Expert -> Project: collaboration/relevance label.
- Expert -> Expert: co-author/co-participant/shared project.
- Funder/Enterprise directions neu co label du tin cay.

Reward:

- Den dung target: reward cao.
- Den dung target type nhung sai target: reward nho.
- Path ngan va relation co y nghia: bonus.
- Path qua node rejected/disabled/merge_required/private: penalty hoac invalid.
- Candidate da co quan he truc tiep neu bai toan la goi y co hoi moi: exclude hoac penalty.

## 6. Path validity va XAI quality gate

Moi path do Inductive PGPR candidate tao ra phai qua quality gate:

- Path chi dung relation trong `ALLOWED_ACTION_RELATIONS`.
- Path khong chua node `rejected`, `disabled`, `merge_required`.
- Path khong chua `owner_only` cua user khac.
- Target phai qua `CandidateMaskService`.
- Intermediate node phai co `allow_as_intermediate_node != false`.
- Path phai convert duoc thanh explanation tieng Viet.
- Neu khong co path ro, khong duoc claim `path_supported`.

Evidence level de nghi:

- `inductive_pgpr_path`: co path hop le va policy score.
- `inductive_pgpr_embedding_only`: co policy/embedding signal nhung path khong du ro.
- `inductive_pgpr_weak`: score thap, path ngan/y nhieu hoac evidence yeu.

Inductive PGPR phai tai su dung rule XAI/candidate mask hien co, khong tao chuan rieng lam lech semantics cua he thong.

## 7. Roadmap

### Phase -1 - Feasibility Check

- Kiem tra node/edge/label/cold-start cases.
- Kiem tra PyTorch Geometric hoac fallback implementation.
- Neu data qua it, chi lam prototype va `promote_allowed=false`.

### Phase 0 - Freeze Baseline & Evaluation

- Chay lai evaluation hien tai.
- Luu baseline PGPR classic, Cypher, embedding only, hybrid.
- Ghi latency p50/p95, NDCG@5, MRR, coverage, cold-start success rate, explanation coverage.

Output:

- `evaluation_baseline_inductive_pgpr_before.json`
- Markdown report so sanh.

### Phase 1 - Snapshot + Feature + Action Schema

- Mo rong `export_graph_snapshot.py`.
- Sanitize training graph.
- Dinh nghia `ALLOWED_ACTION_RELATIONS`.
- Dinh nghia relation direction xuoi/nguoc.
- Dinh nghia max path length theo task.
- Mo rong feature encoder cho tat ca node type.

### Phase 2 - Train GraphSAGE Encoder

- Train encoder tren snapshot.
- Luu candidate artifact rieng.
- Evaluate embedding-only voi baseline.
- Khong thay worker/runtime production.

### Phase 3 - Build InductiveKGEnv

- Tao env moi.
- Lay action tu snapshot cache hoac Neo4j.
- Ap dung action schema + governance mask.
- Test source node moi, public/personal/admin_debug mode.

### Phase 4 - Policy Network Prototype

- Tao `InductivePolicyNetwork`.
- Forward pass voi batch actions.
- Test action mask.
- Test node moi khong co vocab id.
- Chua train production.

### Phase 5 - Offline Training

- Train voi REINFORCE/actor-critic.
- Log reward, success rate, target hit rate, path length.
- Luu:

```text
backend/artifacts/models/inductive_pgpr_v1_candidate/
```

- Neu data qua it hoac metric yeu, report `promote_allowed=false`.

### Phase 6 - Offline Inference Evaluation

- Chay inference offline tren eval set.
- So sanh:
  - PGPR classic.
  - Cypher fallback.
  - GraphSAGE embedding only.
  - Hybrid hien tai.
  - Inductive PGPR candidate.
- Kiem tra path validity/XAI quality gate.

### Phase 7 - Shadow Mode Runtime

- Them mode:

```text
RECOMMENDATION_POLICY_MODE=classic|hybrid|inductive_shadow|inductive
```

- Shadow mode chay candidate nhung khong tra cho user.
- Ghi log/report de so sanh voi hybrid.
- Neu candidate loi, API van fallback ve hybrid hien tai.

### Phase 8 - Promote/Rollback

- Chi promote neu regression gate pass.
- Bat truoc cho admin/internal.
- Theo doi latency, error, coverage, XAI quality.
- Co rollback ve hybrid hien tai.

## 8. Metrics va regression gate

Metrics:

- NDCG@5.
- MRR.
- Recall@5.
- Coverage.
- Cold-start success rate.
- Explanation coverage.
- Path validity rate.
- XAI conversion success rate.
- Latency p50/p95.

Chi promote khi:

- Cold-start success rate tang ro.
- NDCG/MRR khong giam qua threshold.
- Path validity rate dat nguong.
- Explanation coverage khong giam.
- Latency chap nhan duoc.
- Khong co private/rejected/disabled leakage.

## 9. Rui ro ky thuat

- Du lieu hien tai con nho, model deep learning co the khong vuot baseline.
- Runtime rollout cham neu moi buoc query Neo4j.
- Policy cu khong tai su dung nguyen ven; can train policy moi.
- XAI co the kem hon neu path do policy moi tim khong on dinh.
- Node moi co embedding nhung khong co feature/neighbor thi van `no_signal`.
- Action space neu khong freeze co the di qua private/governance relation.

## 10. Cach giam rui ro

- Giu hybrid hien tai lam fallback chinh.
- Bat dau bang feasibility check va offline evaluation.
- Chay shadow mode truoc khi promote.
- Cache embedding/action.
- Gioi han top-k action moi buoc.
- Dung chung `CandidateMaskService`.
- Dung path validity/XAI quality gate.
- Khong promote neu data qua it hoac regression gate fail.

## 11. Ket luan de dua vao bao cao

Huong nghien cuu nay khong thay the ngay PGPR/hybrid hien tai, ma de xuat mot **Inductive PGPR candidate**. Candidate nay tich hop GraphSAGE encoder vao policy de sinh node embedding dong, giup policy co kha nang suy luan voi node moi tot hon ma khong can retrain vocab sau moi entity moi.

Tuy nhien, do du lieu hien tai con nho, huong nay nen duoc trien khai nhu research lifecycle/prototype truoc. He thong chi nen promote candidate khi vuot hybrid baseline qua evaluation, path validity gate, XAI quality gate va co rollback an toan.
