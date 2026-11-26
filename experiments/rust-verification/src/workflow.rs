//! Canonical execution routing over trusted harness receipts.

use serde::{Deserialize, Serialize};
use std::{error::Error, fmt, str::FromStr};
use uuid::Uuid;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(try_from = "String")]
pub struct Sha(String);

impl Sha {
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl fmt::Display for Sha {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        self.0.fmt(formatter)
    }
}

impl TryFrom<String> for Sha {
    type Error = &'static str;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        if matches!(value.len(), 40 | 64)
            && value
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        {
            Ok(Self(value))
        } else {
            Err("expected a full lowercase Git SHA")
        }
    }
}

impl FromStr for Sha {
    type Err = &'static str;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        value.to_owned().try_into()
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Attempt {
    attempt_id: Uuid,
    run_id: Uuid,
    start_sha: Sha,
}

impl Attempt {
    pub fn new(run_id: Uuid, start_sha: Sha) -> Self {
        Self {
            attempt_id: Uuid::new_v4(),
            run_id,
            start_sha,
        }
    }

    pub fn id(&self) -> Uuid {
        self.attempt_id
    }

    pub fn run_id(&self) -> Uuid {
        self.run_id
    }

    pub fn start_sha(&self) -> &Sha {
        &self.start_sha
    }

    pub fn candidate(&self, candidate_sha: Sha) -> Candidate {
        Candidate {
            attempt_id: self.attempt_id,
            candidate_sha,
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Candidate {
    attempt_id: Uuid,
    candidate_sha: Sha,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, Hash, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Stage {
    Intake,
    Design,
    Plan,
    Build,
    Test,
    Review,
    Package,
}

impl Stage {
    pub const ORDER: [Self; 7] = [
        Self::Intake,
        Self::Design,
        Self::Plan,
        Self::Build,
        Self::Test,
        Self::Review,
        Self::Package,
    ];

    fn admits(self, outcome: Outcome) -> bool {
        use Outcome::*;
        match outcome {
            Succeeded | Failed => true,
            Cancelled => self != Self::Package,
            NeedsClarification => matches!(self, Self::Design | Self::Build),
            NeedsRescoping => matches!(self, Self::Plan | Self::Build),
            TestFailed => self == Self::Test,
            ChangesRequired => self == Self::Review,
        }
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Outcome {
    Succeeded,
    Failed,
    Cancelled,
    NeedsClarification,
    NeedsRescoping,
    TestFailed,
    ChangesRequired,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Receipt {
    pub stage: Stage,
    pub outcome: Outcome,
    pub candidate: Option<Candidate>,
}

#[derive(Debug, Eq, PartialEq)]
pub enum InvalidTransition {
    OutOfOrder,
    Outcome,
    Candidate,
}

impl fmt::Display for InvalidTransition {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::OutOfOrder => "receipt must match the next canonical stage",
            Self::Outcome => "outcome is invalid for this stage",
            Self::Candidate => "candidate does not match the stage and attempt",
        })
    }
}

impl Error for InvalidTransition {}

#[derive(Debug)]
pub struct Workflow {
    attempt: Attempt,
    next_index: usize,
    candidate: Option<Candidate>,
    receipts: Vec<Receipt>,
}

impl Workflow {
    pub fn new(attempt: Attempt) -> Self {
        Self {
            attempt,
            next_index: 0,
            candidate: None,
            receipts: Vec::new(),
        }
    }

    pub fn replay(
        attempt: Attempt,
        receipts: impl IntoIterator<Item = Receipt>,
    ) -> Result<Self, InvalidTransition> {
        let mut workflow = Self::new(attempt);
        for receipt in receipts {
            workflow.accept(receipt)?;
        }
        Ok(workflow)
    }

    pub fn next_stage(&self) -> Option<Stage> {
        Stage::ORDER.get(self.next_index).copied()
    }

    pub fn receipts(&self) -> &[Receipt] {
        &self.receipts
    }

    pub fn accept(&mut self, receipt: Receipt) -> Result<(), InvalidTransition> {
        let Receipt {
            stage,
            outcome,
            candidate,
        } = &receipt;
        if self.next_stage() != Some(*stage) {
            return Err(InvalidTransition::OutOfOrder);
        }
        if !stage.admits(*outcome) {
            return Err(InvalidTransition::Outcome);
        }
        match (stage, outcome, candidate) {
            (Stage::Build, Outcome::Succeeded, Some(candidate))
                if candidate.attempt_id == self.attempt.attempt_id =>
            {
                self.candidate = Some(candidate.clone());
            }
            (Stage::Test | Stage::Review, _, Some(candidate))
                if self.candidate.as_ref() == Some(candidate) => {}
            (Stage::Build, Outcome::Succeeded, _)
            | (Stage::Test | Stage::Review, _, _)
            | (_, _, Some(_)) => {
                return Err(InvalidTransition::Candidate);
            }
            _ => {}
        }
        self.next_index = match (stage, outcome) {
            (Stage::Package, _) => Stage::ORDER.len(),
            (_, Outcome::Succeeded) => self.next_index + 1,
            _ => Stage::ORDER.len() - 1,
        };
        self.receipts.push(receipt);
        Ok(())
    }
}
