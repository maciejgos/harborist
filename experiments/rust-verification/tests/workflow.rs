use harborist_verify::workflow::{Attempt, Candidate, Outcome, Receipt, Sha, Stage, Workflow};

fn sha(digit: char) -> Sha {
    digit.to_string().repeat(40).parse().unwrap()
}

fn receipt(stage: Stage, outcome: Outcome, candidate: Option<Candidate>) -> Receipt {
    Receipt {
        stage,
        outcome,
        candidate,
    }
}

fn attempt() -> Attempt {
    Attempt::new(uuid::Uuid::new_v4(), sha('a'))
}

fn built_workflow() -> (Workflow, Attempt, Candidate) {
    let attempt = attempt();
    let candidate = attempt.candidate(sha('b'));
    let mut workflow = Workflow::new(attempt.clone());
    for stage in [Stage::Intake, Stage::Design, Stage::Plan] {
        workflow
            .accept(receipt(stage, Outcome::Succeeded, None))
            .unwrap();
    }
    workflow
        .accept(receipt(
            Stage::Build,
            Outcome::Succeeded,
            Some(candidate.clone()),
        ))
        .unwrap();
    (workflow, attempt, candidate)
}

#[test]
fn failed_test_routes_directly_to_package() {
    let (mut workflow, _, candidate) = built_workflow();
    workflow
        .accept(receipt(
            Stage::Test,
            Outcome::TestFailed,
            Some(candidate.clone()),
        ))
        .unwrap();
    assert_eq!(workflow.next_stage(), Some(Stage::Package));
    assert!(
        workflow
            .accept(receipt(
                Stage::Review,
                Outcome::Succeeded,
                Some(candidate.clone())
            ))
            .is_err()
    );
    workflow
        .accept(receipt(Stage::Package, Outcome::Succeeded, None))
        .unwrap();
    assert_eq!(workflow.next_stage(), None);
}

#[test]
fn test_and_review_must_use_the_exact_build_candidate() {
    let (mut workflow, attempt, candidate) = built_workflow();
    let wrong_attempt = self::attempt().candidate(sha('b'));
    assert!(
        workflow
            .accept(receipt(
                Stage::Test,
                Outcome::Succeeded,
                Some(wrong_attempt)
            ))
            .is_err()
    );
    workflow
        .accept(receipt(
            Stage::Test,
            Outcome::Succeeded,
            Some(candidate.clone()),
        ))
        .unwrap();
    let wrong_revision = attempt.candidate(sha('c'));
    assert!(
        workflow
            .accept(receipt(
                Stage::Review,
                Outcome::Succeeded,
                Some(wrong_revision)
            ))
            .is_err()
    );
    workflow
        .accept(receipt(
            Stage::Review,
            Outcome::Succeeded,
            Some(candidate.clone()),
        ))
        .unwrap();
    assert_eq!(workflow.next_stage(), Some(Stage::Package));
}

#[test]
fn only_the_allowed_outcomes_can_advance_a_stage() {
    let mut workflow = Workflow::new(attempt());
    assert!(
        workflow
            .accept(receipt(Stage::Design, Outcome::Succeeded, None))
            .is_err()
    );
    workflow
        .accept(receipt(Stage::Intake, Outcome::Succeeded, None))
        .unwrap();
    assert!(
        workflow
            .accept(receipt(Stage::Design, Outcome::NeedsRescoping, None))
            .is_err()
    );
    workflow
        .accept(receipt(Stage::Design, Outcome::NeedsClarification, None))
        .unwrap();
    assert_eq!(workflow.next_stage(), Some(Stage::Package));
}
