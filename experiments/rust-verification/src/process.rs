use std::io::{self, Read};
use std::os::fd::{AsRawFd, RawFd};
use std::os::unix::process::{CommandExt, ExitStatusExt};
use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

pub struct Capture {
    pub returncode: i32,
    pub timed_out: bool,
    pub stdout: Stream,
    pub stderr: Stream,
}

#[derive(Default)]
pub struct Stream {
    pub bytes: Vec<u8>,
    pub truncated: bool,
}

struct ProcessGroup(Child);

impl ProcessGroup {
    fn terminate(&self) {
        // The child is the leader of a new process group.
        unsafe { libc::kill(-(self.0.id() as libc::pid_t), libc::SIGKILL) };
    }
}

impl Drop for ProcessGroup {
    fn drop(&mut self) {
        self.terminate();
        let _ = self.0.wait();
    }
}

fn nonblocking(fd: RawFd) -> io::Result<libc::pollfd> {
    // fcntl takes the open pipe descriptor and adds O_NONBLOCK.
    if unsafe { libc::fcntl(fd, libc::F_SETFL, libc::O_NONBLOCK) } == -1 {
        return Err(io::Error::last_os_error());
    }
    Ok(libc::pollfd {
        fd,
        events: libc::POLLIN,
        revents: 0,
    })
}

fn drain(
    pipe: &mut impl Read,
    poll: &mut libc::pollfd,
    stream: &mut Stream,
    limit: usize,
) -> io::Result<()> {
    if poll.revents == 0 {
        return Ok(());
    }
    let mut chunk = [0; 65536];
    match pipe.read(&mut chunk) {
        Ok(0) => poll.fd = -1,
        Ok(size) => {
            let retained = size.min(limit - stream.bytes.len());
            stream.bytes.extend_from_slice(&chunk[..retained]);
            stream.truncated |= retained < size;
        }
        Err(error) if error.kind() == io::ErrorKind::WouldBlock => (),
        Err(error) => return Err(error),
    }
    Ok(())
}

pub fn capture(
    command: &str,
    workspace: &Path,
    allowance: Duration,
    limit: usize,
    cancellation: Option<&Path>,
) -> io::Result<Capture> {
    let mut shell = Command::new("/bin/sh");
    shell
        .args(["-c", command])
        .current_dir(workspace)
        .stdin(Stdio::null());
    capture_cancellable(&mut shell, allowance, limit, cancellation)
}

pub fn capture_command(
    command: &mut Command,
    allowance: Duration,
    limit: usize,
) -> io::Result<Capture> {
    capture_cancellable(command, allowance, limit, None)
}

pub fn capture_cancellable(
    command: &mut Command,
    allowance: Duration,
    limit: usize,
    cancellation: Option<&Path>,
) -> io::Result<Capture> {
    capture_until(command, allowance, limit, || {
        cancellation.map_or(Ok(()), crate::retirement::cancelled)
    })
}

pub fn capture_until(
    command: &mut Command,
    allowance: Duration,
    limit: usize,
    check: impl Fn() -> io::Result<()>,
) -> io::Result<Capture> {
    check()?;
    let deadline = Instant::now() + allowance;
    #[cfg(target_os = "linux")]
    {
        let parent = std::process::id() as libc::pid_t;
        // Only async-signal-safe calls run between fork and exec.
        unsafe {
            command.pre_exec(move || {
                if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0 {
                    return Err(io::Error::last_os_error());
                }
                if libc::getppid() != parent {
                    return Err(io::Error::from_raw_os_error(libc::ECHILD));
                }
                Ok(())
            });
        }
    }
    let mut group = ProcessGroup(
        command
            .process_group(0)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()?,
    );
    let mut stdout = group.0.stdout.take().unwrap();
    let mut stderr = group.0.stderr.take().unwrap();
    let mut fds = [
        nonblocking(stdout.as_raw_fd())?,
        nonblocking(stderr.as_raw_fd())?,
    ];
    let mut out = Stream::default();
    let mut err = Stream::default();
    let mut timed_out = false;

    loop {
        check()?;
        let remaining = deadline.saturating_duration_since(Instant::now());
        let mut status = group.0.try_wait()?;
        if status.is_none() && remaining.is_zero() {
            timed_out = true;
            group.terminate();
            status = Some(group.0.wait()?);
        }
        if status.is_some() {
            group.terminate();
        }
        let timeout = if status.is_some() {
            0
        } else {
            remaining.as_millis().clamp(1, 50) as libc::c_int
        };
        // The descriptors remain owned by stdout and stderr throughout polling.
        let ready = unsafe { libc::poll(fds.as_mut_ptr(), fds.len() as libc::nfds_t, timeout) };
        if ready < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(error);
        }
        drain(&mut stdout, &mut fds[0], &mut out, limit)?;
        drain(&mut stderr, &mut fds[1], &mut err, limit)?;
        if let Some(status) = status {
            if ready == 0 || remaining.is_zero() {
                out.truncated |= fds[0].fd >= 0;
                err.truncated |= fds[1].fd >= 0;
                return Ok(Capture {
                    returncode: status.code().unwrap_or_else(|| -status.signal().unwrap()),
                    timed_out,
                    stdout: out,
                    stderr: err,
                });
            }
        }
    }
}
