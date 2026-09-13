# kumi diagrams

All diagrams are Mermaid, so they are diagrams-as-code: the source lives in this file and GitHub renders them with no build step. Each diagram is one level of the system, from the whole team down to how a single specialist runs and how you add a new one.

## 1. The whole system

The top level. You call `yui`, the coordinator, and it routes to the right specialist. You can also call any specialist directly by name.

```mermaid
graph TD
    U([You])
    U -->|/yui| Y[yui, coordinator]
    U -.call any specialist directly.-> DIRECT([/jaan /mart /ren ...])

    Y --> GO
    Y --> NG
    Y --> IOS
    Y --> PY
    Y --> RE
    Y --> DB
    Y --> XC

    subgraph GO[Go]
        jaan[jaan, implement]
        siim[siim, debug]
        mart[mart, review]
    end
    subgraph NG[Angular]
        liis[liis, implement]
        kadi[kadi, debug]
        tiiu[tiiu, review]
    end
    subgraph IOS[iOS]
        ren[ren, implement]
        shu[shu, debug]
        ryo[ryo, review]
    end
    subgraph PY[Python]
        eero[eero, implement]
        anu[anu, debug]
        ivo[ivo, review]
    end
    subgraph RE[React]
        noa[noa, implement]
        rui[rui, debug]
        aki[aki, review]
    end
    subgraph DB[Data]
        saku[saku, SQL]
        remo[remo, NoSQL]
    end
    subgraph XC[Cross-cutting]
        kai[kai, architect, any stack]
        enn[enn, process manager]
    end
```

## 2. How specialists hand off

Specialists are not isolated. Within a stack, work flows design -> implement -> review, and debug -> review. The coordinator sequences these; the arrows show the natural handoffs.

```mermaid
graph LR
    subgraph Go
        kai -->|spec| jaan
        jaan -->|for review| mart
        siim -->|for review| mart
        mart -.findings.-> jaan
        mart -.findings.-> siim
    end
    subgraph Angular
        liis -->|for review| tiiu
        kadi -->|for review| tiiu
        tiiu -.findings.-> liis
        tiiu -.findings.-> kadi
    end
    subgraph iOS
        ren -->|for review| ryo
        shu -->|for review| ryo
        ryo -.findings.-> ren
        ryo -.findings.-> shu
    end
```

## 3. A feature, end to end

A concrete multi-role task, "build a new endpoint with tests", as the coordinator sequences design, build, and review, passing context through shared state.

```mermaid
sequenceDiagram
    actor You
    participant yui
    participant kai
    participant jaan
    participant mart
    participant State as .kumi state

    You->>yui: build endpoint X with tests
    yui->>kai: design the shape
    kai->>State: write decisions/kai/endpoint-x.md
    kai-->>yui: spec ready
    yui->>jaan: implement per spec
    jaan->>State: read handoff, write decisions/jaan/endpoint-x.md
    jaan-->>yui: implemented + tests, go vet clean
    yui->>mart: review before merge
    mart->>State: read handoff
    mart-->>yui: findings (ranked) or approve
    yui-->>You: relayed result
```

## 4. The uniform triad (why the team is consistent)

Each language stack is the same shape: an implementer, a debugger, a reviewer. Learn one stack and you know how the others relate. Adding a new stack is adding another trio.

```mermaid
graph TD
    subgraph Pattern[Uniform per-stack pattern]
        I[Implementer<br/>read - build - verify]
        D[Debugger<br/>reproduce - root cause - fix]
        R[Reviewer<br/>read-only - rank findings]
        I --> R
        D --> R
        R -.findings.-> I
        R -.findings.-> D
    end
    Pattern -.instantiated as.-> GO[Go: jaan, siim, mart]
    Pattern -.instantiated as.-> NG[Angular: liis, kadi, tiiu]
    Pattern -.instantiated as.-> IOS[iOS: ren, shu, ryo]
    Pattern -.add a stack.-> NEW[e.g. Python: a new trio]
```

## 5. Shared state

For multi-role work, roles communicate only through a uniform state format under `.kumi/` in the working project. No role reads another role's internals; they read the handoff.

```mermaid
graph LR
    subgraph kumi[.kumi/ shared state]
        status[status.md<br/>phase tracking]
        handoff[handoff.md<br/>current context]
        decisions[decisions/&lt;role&gt;/&lt;slug&gt;.md]
    end
    kai -->|writes| decisions
    jaan -->|reads handoff, writes| decisions
    mart -->|reads handoff| decisions
    yui -->|updates| status
    yui -->|updates| handoff
```

## 6. Adding a specialist

Adding a role is mechanical because of the uniform contract. Three steps, and the validator is the gate.

```mermaid
graph TD
    A[Copy template/skill-template/SKILL.md<br/>to skills/&lt;name&gt;/SKILL.md] --> B[Fill the fixed sections]
    B --> C[Add one row to yui's role table]
    C --> D{Run validate_skills.py}
    D -->|pass| E[Valid specialist, nothing else changes]
    D -->|fail| B
```

Nothing else in the plugin changes: the coordinator only learns the new role table row, and no existing specialist is touched.
