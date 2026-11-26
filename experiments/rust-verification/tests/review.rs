use harborist_verify::review::{Review, ReviewError, Specification};
use harborist_verify::workflow::{Attempt, Outcome};

fn candidate() -> harborist_verify::workflow::Candidate {
    let sha = "a".repeat(40).parse().unwrap();
    Attempt::new(uuid::Uuid::new_v4(), sha).candidate("b".repeat(40).parse().unwrap())
}

#[test]
fn extracts_declared_criteria_and_ignores_fenced_examples() {
    let spec =
        Specification::parse("# AC-001: One\n\n```md\n- AC-002: Example\n```\n* AC-003 — Three")
            .unwrap();
    assert_eq!(spec.criterion_ids(), ["AC-001", "AC-003"]);
    assert_eq!(spec.sha256().len(), 64);
    assert!(Specification::parse("- AC-001: One\n- AC-001: Duplicate").is_err());
}

#[test]
fn review_requires_exact_coverage_and_candidate_identity() {
    let spec = Specification::parse("- AC-001: One\n- AC-002: Two").unwrap();
    let expected = candidate();
    let mut output = serde_json::json!({
        "stage": "review", "status": "ready", "candidate": expected,
        "criteria": [
            {"criterion_id":"AC-002","status":"unverified"},
            {"criterion_id":"AC-001","status":"pass"}
        ]
    });

    let review = Review::parse(&output.to_string()).unwrap();
    assert_eq!(
        review.receipt(&expected, &spec).unwrap().outcome,
        Outcome::ChangesRequired
    );
    assert_eq!(
        review.receipt(&candidate(), &spec),
        Err(ReviewError::Candidate)
    );

    output["criteria"][0]["status"] = "pass".into();
    let review = Review::parse(&output.to_string()).unwrap();
    assert_eq!(
        review.receipt(&expected, &spec).unwrap().outcome,
        Outcome::Succeeded
    );

    output["criteria"].as_array_mut().unwrap().pop();
    let review = Review::parse(&output.to_string()).unwrap();
    assert_eq!(review.receipt(&expected, &spec), Err(ReviewError::Coverage));
}
