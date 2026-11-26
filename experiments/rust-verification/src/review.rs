//! Specification declarations and independent REVIEW validation.

use crate::workflow::{Candidate, Outcome, Receipt, Stage};
use regex::Regex;
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::{collections::HashSet, error::Error, fmt, sync::LazyLock};

static DECLARATION: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^\s{0,3}(?:#{1,6}\s+|[-*+]\s+)?(AC-[0-9]{3,})\s*(?::|—|–| -)\s*(.*)$")
        .expect("fixed criterion pattern")
});
static FENCE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^\s{0,3}(`{3,}|~{3,})(.*)$").expect("fixed fence pattern"));

#[derive(Debug)]
pub struct Specification {
    sha256: String,
    criterion_ids: Vec<String>,
}

impl Specification {
    pub fn parse(markdown: &str) -> Result<Self, ReviewError> {
        let mut ids = HashSet::new();
        let mut criterion_ids = Vec::new();
        let mut fence: Option<&str> = None;
        for line in markdown.lines() {
            if let Some(active) = fence {
                if let Some(marker) = FENCE.captures(line) {
                    if marker[1].starts_with(active) && marker[2].trim().is_empty() {
                        fence = None;
                    }
                }
                continue;
            }
            if let Some(marker) = FENCE.captures(line) {
                fence = marker.get(1).map(|value| value.as_str());
                continue;
            }
            if let Some(declaration) = DECLARATION.captures(line) {
                let id = declaration.get(1).expect("required capture").as_str();
                if declaration[2].trim().is_empty() || !ids.insert(id) {
                    return Err(ReviewError::Specification);
                }
                criterion_ids.push(id.to_owned());
            }
        }
        if criterion_ids.is_empty() {
            return Err(ReviewError::Specification);
        }
        Ok(Self {
            sha256: format!("{:x}", Sha256::digest(markdown.as_bytes())),
            criterion_ids,
        })
    }

    pub fn sha256(&self) -> &str {
        &self.sha256
    }

    pub fn criterion_ids(&self) -> &[String] {
        &self.criterion_ids
    }
}

#[derive(Deserialize, Debug)]
#[serde(tag = "stage", rename_all = "snake_case", deny_unknown_fields)]
enum StageResult {
    Review {
        status: Ready,
        candidate: Candidate,
        criteria: Vec<Criterion>,
    },
}

#[derive(Deserialize, Debug)]
#[serde(rename_all = "snake_case")]
enum Ready {
    Ready,
}

#[derive(Deserialize, Debug)]
#[serde(deny_unknown_fields)]
struct Criterion {
    criterion_id: String,
    status: CriterionStatus,
}

#[derive(Deserialize, Debug, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
enum CriterionStatus {
    Pass,
    Fail,
    Unverified,
}

#[derive(Debug)]
pub struct Review {
    candidate: Candidate,
    criteria: Vec<Criterion>,
}

impl Review {
    pub fn parse(json: &str) -> Result<Self, ReviewError> {
        let StageResult::Review {
            status: Ready::Ready,
            candidate,
            criteria,
        } = serde_json::from_str(json).map_err(|_| ReviewError::InvalidOutput)?;
        let mut ids = HashSet::new();
        if criteria.is_empty()
            || criteria.iter().any(|item| {
                let id = item.criterion_id.as_str();
                id.is_empty() || id != id.trim() || !ids.insert(id)
            })
        {
            return Err(ReviewError::InvalidOutput);
        }
        Ok(Self {
            candidate,
            criteria,
        })
    }

    pub fn receipt(
        &self,
        expected: &Candidate,
        spec: &Specification,
    ) -> Result<Receipt, ReviewError> {
        if &self.candidate != expected {
            return Err(ReviewError::Candidate);
        }
        let required: HashSet<_> = spec.criterion_ids().iter().collect();
        let reviewed: HashSet<_> = self
            .criteria
            .iter()
            .map(|item| &item.criterion_id)
            .collect();
        if required != reviewed {
            return Err(ReviewError::Coverage);
        }

        let outcome = if self
            .criteria
            .iter()
            .all(|item| item.status == CriterionStatus::Pass)
        {
            Outcome::Succeeded
        } else {
            Outcome::ChangesRequired
        };
        Ok(Receipt {
            stage: Stage::Review,
            outcome,
            candidate: Some(expected.clone()),
        })
    }
}

#[derive(Debug, Eq, PartialEq)]
pub enum ReviewError {
    Specification,
    InvalidOutput,
    Candidate,
    Coverage,
}

impl fmt::Display for ReviewError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::Specification => "specification must declare unique criteria with text",
            Self::InvalidOutput => "invalid structured REVIEW output",
            Self::Candidate => "REVIEW must assess the exact candidate",
            Self::Coverage => "REVIEW must cover exactly the required specification criteria",
        })
    }
}

impl Error for ReviewError {}
