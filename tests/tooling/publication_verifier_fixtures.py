from scripts.publication_verifier_service import CommandResult

SHA = "a" * 40


class FakeRunner:
    def __init__(self, results: tuple[CommandResult, ...]) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.results: list[CommandResult] = list(results)

    def run(self, arguments: tuple[str, ...]) -> CommandResult:
        self.calls.append(arguments)
        return self.results.pop(0)


def result(stdout: str) -> CommandResult:
    return CommandResult(0, stdout, "")


def target(is_empty: bool, permission: str = "ADMIN") -> str:
    return f'{{"nameWithOwner":"Tommynem/opatchy","isEmpty":{str(is_empty).lower()},"viewerPermission":"{permission}"}}'


def registry(active: str = "other.plugin", retired: str = "[]") -> str:
    return f'{{"sources":[{{"type":"suite"}},{{"plugins":{{"{active}":{{}}}}}}],"retiredPluginIds":{retired}}}'


def marketplace(document: str) -> tuple[CommandResult, ...]:
    return (
        result('{"defaultBranchRef":{"name":"main"}}'),
        result(f"{SHA}\n"),
        result(document),
    )


def issue(slug: str = "verifier") -> str:
    return f'{{"body":"<!-- opatchy-roadmap-slug: {slug} -->","url":"https://example.invalid/1","labels":[{{"name":"enhancement"}},{{"name":"roadmap"}}]}}'


def published_prefix(
    issues: str, conclusion: str = "success"
) -> tuple[CommandResult, ...]:
    repository = '{"nameWithOwner":"Tommynem/opatchy","visibility":"PUBLIC","url":"https://github.com/Tommynem/opatchy","hasIssuesEnabled":true,"defaultBranchRef":{"name":"main"}}'
    ci = f'{{"headSha":"{SHA}","status":"completed","conclusion":"{conclusion}","url":"https://example.invalid/run"}}'
    return (
        result("Tommynem\n"),
        result("git@github.com:Tommynem/opatchy.git\n"),
        result(f"{SHA}\n"),
        result(repository),
        result(f"{SHA}\n"),
        result(f"[{issues}]"),
        result(f"[{ci}]"),
        result("[]"),
        result("[]"),
    )
