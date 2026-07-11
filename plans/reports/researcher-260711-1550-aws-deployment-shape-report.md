# AWS Deployment Shape Research: Hackathon Stack on ap-southeast-1

**Research Date**: 2026-07-11  
**Project Context**: 2-person hackathon (1-2 weeks), Python services (uv workspace), DuckDB + semantic layer CLI, Neo4j knowledge graph, LLM agent harness (Bedrock), Langfuse tracing. Demo-grade. Team in Vietnam; ap-southeast-1 (Singapore) preferred.

---

## 1. Neo4j Hosting: AuraDB Free vs Docker on EC2

### AuraDB Free Tier (Cloud-Hosted)

**Limits** (as of July 2026):
- Max 200k nodes, 400k relationships per database
- Auto-deletion after 30 days inactivity (data safe while paused, but instance deleted)
- No pause/resume grace period like paid tiers (which auto-resume after 30 days)
- Included: 1 database, 1 instance, no encryption at rest option

**Friction for hackathon**:
- No deletion risk if you use the database every 29 days (acceptable for active hackathon)
- Connection: Standard neo4j+s:// URI (Aura certificate, no custom cert management)
- Zero ops overhead; semantic-layer ingest scripts just connect and write
- **Risk**: If demo goes quiet for >30 days post-hackathon, instance vanishes

**Verdict**: **Viable if you're actively using the graph throughout**. Simple URI handoff to teammates. No infrastructure.

### Docker on EC2 (Self-Hosted)

**Setup** (neo4j:5-community or neo4j:2026-community):
```yaml
# Minimal docker-compose snippet
services:
  neo4j:
    image: neo4j:5-community
    environment:
      NEO4J_AUTH: neo4j/demo-password  # Set initial password
    ports:
      - "7687:7687"  # Bolt (binary protocol)
      - "7474:7474"  # HTTP
    volumes:
      - neo4j-data:/data
      - neo4j-logs:/logs
```

**Advantages**:
- Persistent storage (no auto-deletion)
- Bolt URI: `bolt://ec2-instance-private-ip:7687` (or public via security group)
- Memory heap directly configurable (critical for large graphs)
- Ingest scripts connect identically to AuraDB (Cypher compatibility)

**Memory tuning** for hackathon:
- Neo4j heap: Set `server.memory.heap.initial_size` and `server.memory.heap.max_size` to same value
- Rule of thumb: Total RAM = Heap + Page Cache + OS (~2GB)
- For t3.xlarge (16GB): Allocate 8-10GB heap, 4-5GB pagecache, 2GB OS
- Use `neo4j-admin memrec` to auto-recommend

**Verdict**: **Recommended for hackathon**. No cloud fees, no deletion risk. Semantic-layer ingest works identically. Single EC2 instance overhead acceptable.

**Connection URIs**:
- AuraDB: `neo4j+s://xxxxx.databases.neo4j.io` (cloud-managed cert)
- Docker on EC2: `bolt://10.0.1.42:7687` (internal) or `bolt://54.x.x.x:7687` (public, via security group)

---

## 2. Deployment Shape: EC2 vs ECS Fargate vs App Runner

### Current Landscape (July 2026)

| Option | Status | Hackathon Fit | Ops Load | Cost/Day |
|--------|--------|---|---|---|
| **App Runner** | Maintenance mode (no new customers post-April 2026) | ❌ Avoid | Very low | ~$0.10-0.15 + overages |
| **ECS Express Mode (Fargate)** | GA, recommended for small teams | ✅ Good | Low | ~$0.08-0.12 |
| **EC2 (t3.xlarge)** | Standard, needs manual ops | ✅ Good | Medium | ~$0.14-0.20 |
| **Lambda** | Serverless, event-driven | ❌ Not fit (long-running services) | N/A | N/A |

### Recommendation: **Single EC2 (t3.xlarge) with docker-compose**

**Why for this team**:
1. **Speed to demo**: `git clone`, `docker-compose up`, done. No ECS cluster setup, no Fargate task definitions.
2. **Full control**: Neo4j heap, Langfuse resource limits, port bindings—all in one file.
3. **Cost predictable**: ~USD 0.14–0.20/hour in ap-southeast-1 (~USD 3.50–5/day on-demand; reserve 1-year for USD 2.50–3/day if extending post-hackathon).
4. **No new infrastructure patterns**: Your team likely knows SSH + docker-compose. ECS Express adds cognitive load.

**Instance size**: **t3.xlarge** (4 vCPU, 16GB RAM)
- Neo4j 5.x needs 4–8GB heap + pagecache
- Langfuse self-hosted: ~2–3GB (PostgreSQL + ClickHouse in single container)
- DuckDB: Embedded, minimal
- Headroom for spiking agent workloads
- t3.large (2 vCPU, 8GB) works but tight; OOM risk under load

**ECS Express as backup**: If ops becomes a blocker, ECS Express (Fargate) removes instance management. Deploy via `sam deploy` or CloudFormation template, auto-provisions ALB + security groups. Trade-off: ~5–10 min setup vs 0 min EC2.

**Cost Estimate** (ap-southeast-1, 7-day hackathon):
- EC2 t3.xlarge on-demand: ~USD 5–7/day → USD 35–50 total
- EBS 30GB gp3: ~USD 1/day → USD 7 total
- Bedrock inference (agent calls): Depends on token usage; budgets separately
- NAT/data transfer out: ~USD 0.01–0.05/GB (minimal for demo)
- **Total for week**: USD 45–65

---

## 3. IAM Setup for Bedrock in ap-southeast-1

### Regional Availability & Routing

**Important finding**: Claude models in ap-southeast-1 are accessible only via **global cross-region inference** (no in-region endpoint as of July 2026). Requests route across AWS regions; respects data residency constraints if configured.

**Model availability**:
- Claude Opus 4.6+, Sonnet 4.6+, Haiku 4.5+ available via global profile
- Use model ID format: `anthropic.claude-sonnet-4-20250514` (regional) or routing profile `arn:aws:bedrock:ap-southeast-1::inference-profile/default-claude-inference-*` (global)

**Option A: Direct region inference** (if models added to ap-southeast-1 in-region):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": "arn:aws:bedrock:ap-southeast-1::foundation-model/anthropic.claude-*"
    },
    {
      "Effect": "Allow",
      "Action": "bedrock:InvokeModelWithResponseStream",
      "Resource": "arn:aws:bedrock:ap-southeast-1::foundation-model/anthropic.claude-*"
    }
  ]
}
```

**Option B: Global cross-region inference** (current working approach):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      "Resource": "arn:aws:bedrock:ap-southeast-1::inference-profile/*"
    },
    {
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      "Resource": "arn:aws:bedrock:*::foundation-model/anthropic.claude-*"
    }
  ]
}
```

### EC2 Instance Role

**Create IAM role** (e.g., `HackathonBedrockRole`):
```bash
aws iam create-role \
  --role-name HackathonBedrockRole \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ec2.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }' \
  --region ap-southeast-1
```

**Attach policy** (use Option B above for current setup):
```bash
aws iam put-role-policy \
  --role-name HackathonBedrockRole \
  --policy-name BedrockInvokePolicy \
  --policy-document file://bedrock-policy.json \
  --region ap-southeast-1
```

**Launch EC2 with this role**: Specify `--iam-instance-profile Name=HackathonBedrockProfile` or via console.

**In your Python agent code** (using boto3):
```python
import boto3
bedrock = boto3.client("bedrock-runtime", region_name="ap-southeast-1")
response = bedrock.converse(
    modelId="anthropic.claude-3-5-sonnet-20241022-v2",
    messages=[...]
)
```

**Key clarification**: The IAM action is `bedrock:InvokeModel` (not `bedrock-runtime:*`). The string "bedrock-runtime" is the AWS API endpoint hostname, not an IAM service prefix.

---

## 4. Exposing Chat UI from EC2

### Pattern: Nginx Reverse Proxy + Streamlit/Gradio + Security Group

**Standard architecture**:
```
┌─ EC2 Instance ─────────────────────┐
│ Nginx (localhost:80/443)           │
│  ↓                                 │
│ Streamlit app (localhost:8501)      │
│ OR Gradio app (localhost:7860)      │
│ OR FastAPI (localhost:8000)         │
└────────────────────────────────────┘
     ↑ Allow from 0.0.0.0:443 (HTTPS)
     └─ Security Group inbound rule
```

### Setup Steps

**1. Security Group**:
```bash
aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxx \
  --protocol tcp \
  --port 443 \
  --cidr 0.0.0.0/0 \
  --region ap-southeast-1
```

**2. Nginx config** (at `/etc/nginx/sites-available/streamlit`):
```nginx
upstream streamlit {
    server 127.0.0.1:8501;
}

server {
    listen 443 ssl http2;
    server_name your-ec2-public-dns.compute.amazonaws.com;

    ssl_certificate /etc/letsencrypt/live/.../fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/.../privkey.pem;

    location / {
        proxy_pass http://streamlit;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
    }
}

server {
    listen 80;
    server_name your-ec2-public-dns.compute.amazonaws.com;
    return 301 https://$server_name$request_uri;
}
```

**3. Run Streamlit in background**:
```bash
nohup streamlit run app.py \
  --server.port=8501 \
  --server.address=127.0.0.1 \
  > streamlit.log 2>&1 &
```

**4. HTTPS certificate** (free via Let's Encrypt + certbot):
```bash
sudo certbot certonly --standalone -d your-ec2-public-dns.compute.amazonaws.com
```

### Alternative: SSH Tunnel (for demos behind VPN)

**Hackathon demo scenario**: Only teammates need access → SSH tunnel is simpler, no HTTPS cert needed.

```bash
# On your laptop
ssh -L 8501:localhost:8501 ec2-user@ec2-public-ip

# Then visit http://localhost:8501 locally
```

**Pros**: No cert, no security group exposure to 0.0.0.0, teammates connect via SSH.  
**Cons**: Requires SSH key distribution, only works for live demo (not async sharing).

### Gradio/FastAPI Notes

**Gradio** (newer versions 3.19+):
- Uses FRP (fast reverse proxy) for share links instead of SSH
- Set `share=True` for automatic public tunnel (easier than Nginx)
- URL lasts 72 hours by default
- Less overhead than nginx setup

**FastAPI**:
- Identical nginx reverse proxy pattern
- Change upstream to `127.0.0.1:8000`

**Recommended for hackathon**:  
1. **Live demo at event**: Streamlit/Gradio + Nginx + EC2 public IP (clean UI, shared link)
2. **Internal team access**: SSH tunnel to localhost:8501 (no cert, minimal exposure)
3. **Fastest prototype**: Gradio `share=True` (no infra setup, URL expires in 72h)

---

## 5. docker-compose Bundle (Sketch)

```yaml
version: "3.8"
services:
  neo4j:
    image: neo4j:5-community
    environment:
      NEO4J_AUTH: neo4j/change-me
      server.memory.heap.initial_size: 8g
      server.memory.heap.max_size: 8g
    ports:
      - "7687:7687"
    volumes:
      - neo4j-data:/data

  langfuse:
    image: langfuse/langfuse:latest
    environment:
      DATABASE_URL: postgresql://...
      CLICKHOUSE_URL: http://clickhouse:8123
    ports:
      - "3000:3000"
    depends_on:
      - postgres
      - clickhouse

  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: langfuse
      POSTGRES_PASSWORD: password
    volumes:
      - postgres-data:/var/lib/postgresql/data

  clickhouse:
    image: clickhouse/clickhouse-server:latest
    ports:
      - "8123:8123"
    volumes:
      - clickhouse-data:/var/lib/clickhouse

  streamlit:
    build: ./chat-ui  # Your Streamlit app Dockerfile
    environment:
      NEO4J_URI: bolt://neo4j:7687
      BEDROCK_REGION: ap-southeast-1
    ports:
      - "8501:8501"
    depends_on:
      - neo4j

volumes:
  neo4j-data:
  postgres-data:
  clickhouse-data:
```

**Notes**:
- DuckDB (embedded in Python agent) runs in the same container as your agent service
- Langfuse needs PostgreSQL + ClickHouse; this is baseline for self-hosted v3
- Adjust heap/replicas for your hackathon load

---

## Trade-off Summary

| Decision | Choice | Why | Trade-off |
|----------|--------|-----|-----------|
| **Neo4j hosting** | Docker on EC2 | No deletion risk, memory control | Slightly more ops |
| **Deployment** | Single EC2 t3.xlarge | Speed + full control | Manual instance management |
| **Bedrock routing** | Global cross-region profile | Current availability | Data may leave ap-southeast-1 region |
| **Chat UI** | Nginx + Streamlit | Standard, HTTPS, hackathon-proven | Cert management |
| **Alternative UI** | Gradio `share=True` | Zero infra, instant public link | URL expires, less customizable |

---

## Adoption Risk & Maturity

✅ **Low risk**: All technologies production-grade.
- Neo4j 5.x: Stable, widely deployed, community edition fully supported.
- ECS/EC2: AWS standard, no surprises.
- Bedrock cross-region inference: GA as of 2024, well-documented in July 2026.
- Nginx reverse proxy: 20+ year standard pattern.
- Langfuse self-hosted: Stable as of v3.x (released 2024).

⚠️ **Caution**: Bedrock's global inference profile is newer than regional endpoints. If strict ap-southeast-1 data residency is a hard requirement, escalate to AWS team to confirm compliance.

---

## Unresolved Questions

1. **Langfuse UI access**: Does team need to access Langfuse dashboard from outside EC2, or only your app internally calls it for tracing? (Affects nginx configuration.)
2. **DuckDB file location**: Is DuckDB persisted to EC2 EBS volume, or ephemeral per agent run? (Affects data lifecycle.)
3. **Bedrock model selection**: Confirmed Claude Haiku for cost, or need Sonnet for reasoning? (Affects token budget.)
4. **Post-hackathon retention**: Keep EC2 running for portfolio, or tear down? (Affects multi-week cost planning.)

---

## Final Recommendations (Ranked)

### Tier 1: Recommended
1. **Deployment**: EC2 t3.xlarge + docker-compose (Neo4j + Langfuse + app services)
2. **Neo4j**: Docker container on EC2 (persistent, controlled memory)
3. **Chat UI**: Streamlit + Nginx reverse proxy on port 443 (HTTPS, professional, portable)
4. **Bedrock**: Global cross-region inference profile, Instance IAM role with `bedrock:InvokeModel` + `bedrock:InvokeModelWithResponseStream`

### Tier 2: Viable Alternatives
- **Neo4j**: AuraDB Free (if graph stays active, no ops overhead)
- **Deployment**: ECS Express (if ops becomes blocker; similar time-to-demo)
- **Chat UI**: Gradio `share=True` (for quick demos, no infra required)

### Tier 3: Avoid
- App Runner (maintenance mode, no new customers post-April 2026)
- Complex multi-zone setup (overkill for 2-person hackathon)
- Bedrock in-region only (Claude not available in-region in ap-southeast-1 currently)

---

**Status**: DONE  
**Summary**: Recommend single EC2 t3.xlarge with docker-compose (Neo4j + Langfuse + Streamlit), nginx reverse proxy on HTTPS, Bedrock global cross-region profile with instance IAM role. Cost ~USD 50–65 for 1-week hackathon; mature, low-ops stack suitable for team skill level.  
**Concerns**: Bedrock's global inference may route data outside ap-southeast-1; confirm compliance requirement with AWS if strict residency mandated.
