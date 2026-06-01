# Architecture

`src/hermesbench` contains the CLI, task parser, runner, adapters, graders, schemas, and scoring. Tasks live in `tasks/public-dev` with a manifest and reusable template. Fixtures are copied into isolated temp workdirs per task. Results are normalized JSON and can be aggregated locally or uploaded later.
