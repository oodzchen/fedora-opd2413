/* Opt-in diagnostic collector. The caller supplies an approved mounted sink.
 * Completed O_DSYNC writes and directory fsync are not a guarantee against
 * controller failure. Initial loss, sequence gaps and read overruns are distinct.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <getopt.h>
#include <poll.h>
#include <signal.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <sys/utsname.h>
#include <unistd.h>

static volatile sig_atomic_t stopped;
static volatile sig_atomic_t signal_fd = -1;

struct sequence {
    bool have, skip, at_start;
    uint64_t first, last, gaps, malformed, gap_previous, gap_current;
    char prefix[256];
    size_t used;
};

static void stop(int number)
{
    int saved = errno;
    stopped = number;
    if (signal_fd >= 0) {
        const char byte = 1;
        ssize_t ignored = write((int)signal_fd, &byte, 1);
        (void)ignored;
    }
    errno = saved;
}

static int write_all(int fd, const char *data, size_t length)
{
    while (length) {
        ssize_t count = write(fd, data, length);
        if (count < 0 && errno == EINTR)
            continue;
        if (count <= 0) {
            if (!count)
                errno = EIO;
            return -1;
        }
        data += count;
        length -= (size_t)count;
    }
    return 0;
}

static int text(int fd, const char *message)
{
    return write_all(fd, message, strlen(message));
}

static int note(int fd, const char *format, ...) __attribute__((format(printf, 2, 3)));
static int note(int fd, const char *format, ...)
{
    char buffer[1024];
    va_list args;
    va_start(args, format);
    int length = vsnprintf(buffer, sizeof(buffer), format, args);
    va_end(args);
    if (length < 0 || (size_t)length >= sizeof(buffer)) {
        errno = EOVERFLOW;
        return -1;
    }
    return write_all(fd, buffer, (size_t)length);
}

static int metadata(int fd, const char *name, const char *path)
{
    char buffer[8192];
    int input = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    ssize_t count;
    if (input < 0)
        return -1;
    do {
        count = read(input, buffer, sizeof(buffer));
    } while (count < 0 && errno == EINTR);
    close(input);
    if (count <= 0 || count == (ssize_t)sizeof(buffer)) {
        errno = EIO;
        return -1;
    }
    if (note(fd, "# %s=", name) || write_all(fd, buffer, (size_t)count))
        return -1;
    return buffer[count - 1] == '\n' ? 0 : text(fd, "\n");
}

static int notify_ready(void)
{
    const char *name = getenv("NOTIFY_SOCKET");
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    const char message[] = "READY=1\nSTATUS=kmsg history synchronized and integrity checked\n";
    if (!name || (name[0] != '/' && name[0] != '@') ||
        strlen(name) >= sizeof(address.sun_path)) {
        errno = EINVAL;
        return -1;
    }
    size_t length = strlen(name);
    memcpy(address.sun_path, name, length + 1);
    if (name[0] == '@')
        address.sun_path[0] = '\0';
    int fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (fd < 0)
        return -1;
    ssize_t sent;
    do {
        sent = sendto(fd, message, sizeof(message) - 1, MSG_NOSIGNAL,
                      (const struct sockaddr *)&address,
                      (socklen_t)(offsetof(struct sockaddr_un, sun_path) + length + (name[0] != '@')));
    } while (sent < 0 && errno == EINTR);
    int saved = errno;
    close(fd);
    errno = saved;
    return sent == (ssize_t)sizeof(message) - 1 ? 0 : -1;
}

static int report_ready(int output, int *ready_fd, bool notify, bool *announced)
{
    if (*announced)
        return 0;
    if (fdatasync(output) || (notify && notify_ready()))
        return -1;
    if (*ready_fd >= 0) {
        if (text(*ready_fd, "READY\n"))
            return -1;
        close(*ready_fd);
        *ready_fd = -1;
    }
    *announced = true;
    return 0;
}

static bool number(char **cursor, char delimiter, uint64_t *value)
{
    char *start = *cursor, *end;
    if (*start < '0' || *start > '9')
        return false;
    errno = 0;
    uintmax_t parsed = strtoumax(start, &end, 10);
    if (errno || *end != delimiter || parsed > UINT64_MAX)
        return false;
    *value = (uint64_t)parsed;
    *cursor = end + 1;
    return true;
}

static void header(struct sequence *state)
{
    char *cursor = state->prefix;
    uint64_t priority, seq, timestamp;
    if (!number(&cursor, ',', &priority) || !number(&cursor, ',', &seq) ||
        !number(&cursor, ',', &timestamp) || !*cursor) {
        state->malformed++;
        return;
    }
    (void)priority;
    (void)timestamp;
    if (!state->have) {
        state->first = seq;
        state->have = true;
    } else if (state->last == UINT64_MAX || seq != state->last + 1) {
        if (!state->gaps) {
            state->gap_previous = state->last;
            state->gap_current = seq;
        }
        state->gaps++;
    }
    state->last = seq;
}

/* kmsg dictionary lines start with a space. Do not insert annotations between
 * fragmented input chunks: write the original bytes, then summarize at a drain
 * boundary or at exit. Only a bounded header prefix is buffered in RAM.
 */
static void inspect(struct sequence *state, const char *data, size_t length)
{
    for (size_t i = 0; i < length; ++i) {
        unsigned char ch = (unsigned char)data[i];
        if (ch == '\n') {
            if (!state->skip)
                state->malformed++;
            state->skip = false;
            state->at_start = true;
            state->used = 0;
            continue;
        }
        if (state->at_start && ch == ' ')
            state->skip = true;
        state->at_start = false;
        if (state->skip)
            continue;
        if (ch == ';') {
            state->prefix[state->used] = '\0';
            header(state);
            state->skip = true;
        } else if (state->used + 1 < sizeof(state->prefix)) {
            state->prefix[state->used++] = (char)ch;
        } else {
            state->malformed++;
            state->skip = true;
        }
    }
}

static int summary(int fd, const char *stage, const struct sequence *state)
{
    return note(fd, "\n# KMSG_%s have=%d first=%" PRIu64 " last=%" PRIu64
                " initial_missing=%" PRIu64 " gaps=%" PRIu64 " malformed=%" PRIu64
                " partial=%d gap_previous=%" PRIu64 " gap_current=%" PRIu64 "\n",
                stage, state->have, state->first, state->last, state->first,
                state->gaps, state->malformed, !state->at_start,
                state->gap_previous, state->gap_current);
}

int main(int argc, char **argv)
{
    static const struct option options[] = {
        {"output", required_argument, NULL, 'o'},
        {"source", required_argument, NULL, 's'},
        {"ready-fd", required_argument, NULL, 'r'},
        {"notify", no_argument, NULL, 'n'},
        {"require-start-zero", no_argument, NULL, 'z'},
        {NULL, 0, NULL, 0},
    };
    const char *source = "/dev/kmsg", *output = NULL;
    int source_fd = -1, output_fd = -1, directory_fd = -1, ready_fd = -1;
    int wakeup[2] = {-1, -1}, choice, result = EXIT_FAILURE;
    char *path = NULL, *base, *slash, buffer[65536];
    unsigned long overruns = 0;
    bool notify = false, strict = false, announced = false;
    struct sequence sequence = {.at_start = true};
    struct stat info;
    struct utsname system;
    struct sigaction action = {.sa_handler = stop};

    while ((choice = getopt_long(argc, argv, "o:s:r:nz", options, NULL)) != -1) {
        if (choice == 'o')
            output = optarg;
        else if (choice == 's')
            source = optarg;
        else if (choice == 'n')
            notify = true;
        else if (choice == 'z')
            strict = true;
        else if (choice == 'r') {
            char *end;
            errno = 0;
            long value = strtol(optarg, &end, 10);
            if (errno || !*optarg || *end || value < 3 || value > 65535) {
                fprintf(stderr, "invalid readiness fd\n");
                return EXIT_FAILURE;
            }
            ready_fd = (int)value;
            if (fcntl(ready_fd, F_GETFD) < 0) {
                perror("readiness fd");
                return EXIT_FAILURE;
            }
        } else
            goto usage;
    }
    if (!output || optind != argc)
        goto usage;
    if (notify && !getenv("NOTIFY_SOCKET")) {
        fprintf(stderr, "--notify requires NOTIFY_SOCKET\n");
        return EXIT_FAILURE;
    }
    if (pipe2(wakeup, O_CLOEXEC | O_NONBLOCK)) {
        perror("signal pipe");
        goto out;
    }
    signal_fd = wakeup[1];
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGTERM, &action, NULL) || sigaction(SIGINT, &action, NULL)) {
        perror("sigaction");
        goto out;
    }
    signal(SIGPIPE, SIG_IGN);
    source_fd = open(source, O_RDONLY | O_CLOEXEC | O_NONBLOCK | O_NOFOLLOW);
    if (source_fd < 0 || (lseek(source_fd, 0, SEEK_SET) < 0 && errno != ESPIPE)) {
        perror("open/seek source");
        goto out;
    }
    path = strdup(output);
    if (!path) {
        perror("output path");
        goto out;
    }
    slash = strrchr(path, '/');
    base = slash ? slash + 1 : path;
    if (!*base || !strcmp(base, ".") || !strcmp(base, "..")) {
        errno = EINVAL;
        perror("output basename");
        goto out;
    }
    if (slash && slash != path)
        *slash = '\0';
    directory_fd = open(!slash ? "." : slash == path ? "/" : path,
                        O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (directory_fd < 0) {
        perror("open output directory");
        goto out;
    }
    output_fd = openat(directory_fd, base,
                       O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC | O_DSYNC, 0600);
    if (output_fd < 0 || fstat(output_fd, &info) || !S_ISREG(info.st_mode)) {
        perror("create new regular output (will not overwrite)");
        goto out;
    }
    if (uname(&system) ||
        note(output_fd, "# opd2413-bootlog format=1 kernel=%s pid=%ld\n", system.release, (long)getpid()) ||
        metadata(output_fd, "boot_id", "/proc/sys/kernel/random/boot_id") ||
        metadata(output_fd, "cmdline", "/proc/cmdline") ||
        fdatasync(output_fd) || fsync(directory_fd)) {
        perror("persist header/directory");
        goto out;
    }
    while (!stopped) {
        ssize_t count = read(source_fd, buffer, sizeof(buffer));
        if (count > 0) {
            inspect(&sequence, buffer, (size_t)count);
            if (write_all(output_fd, buffer, (size_t)count)) {
                perror("persist record");
                goto out;
            }
            if (strict && (sequence.first || sequence.gaps || sequence.malformed))
                goto integrity_fail;
        } else if (!count || (count < 0 && errno == EAGAIN)) {
            if (strict && (!sequence.have || !sequence.at_start)) {
                if (!count)
                    goto integrity_fail;
                /* A FIFO test may still be sending the first complete record. */
            } else {
                if ((!announced && sequence.at_start && summary(output_fd, "DRAIN", &sequence)) ||
                    report_ready(output_fd, &ready_fd, notify, &announced)) {
                    perror("report readiness");
                    goto out;
                }
            }
            if (!count)
                break;
            struct pollfd events[] = {
                {.fd = source_fd, .events = POLLIN},
                {.fd = wakeup[0], .events = POLLIN},
            };
            if (poll(events, 2, -1) < 0 && errno != EINTR) {
                perror("poll source");
                goto out;
            }
        } else if (errno == EINTR) {
            continue;
        } else if (errno == EPIPE) {
            overruns++;
            if (text(output_fd, "\n# KMSG_OVERRUN: records overwritten while collecting\n")) {
                perror("persist overrun marker");
                goto out;
            }
            if (strict)
                goto integrity_fail;
        } else {
            perror("read source");
            goto out;
        }
    }
    if (strict && (!sequence.have || !sequence.at_start))
        goto integrity_fail;
    if (summary(output_fd, "SUMMARY", &sequence) ||
        note(output_fd, "# END signal=%d overruns=%lu\n", (int)stopped, overruns) || fdatasync(output_fd)) {
        perror("persist end marker");
        goto out;
    }
    result = EXIT_SUCCESS;
    goto out;
integrity_fail:
    fprintf(stderr, "kmsg integrity failed; refusing readiness/continuation\n");
    if (summary(output_fd, "INTEGRITY_FAILURE", &sequence) ||
        text(output_fd, "# INCOMPLETE: initial loss, sequence gap, malformed or unfinished record\n") || fdatasync(output_fd))
        perror("persist incomplete marker");
out:
    signal_fd = -1;
    if (wakeup[0] >= 0)
        close(wakeup[0]);
    if (wakeup[1] >= 0)
        close(wakeup[1]);
    if (ready_fd >= 0)
        close(ready_fd);
    if (output_fd >= 0 && close(output_fd)) {
        perror("close output");
        result = EXIT_FAILURE;
    }
    if (directory_fd >= 0)
        close(directory_fd);
    if (source_fd >= 0)
        close(source_fd);
    free(path);
    return result;
usage:
    fprintf(stderr, "usage: %s --output NEW_FILE [--ready-fd FD] [--notify] [--require-start-zero] [--source TEST_FILE]\n", argv[0]);
    return EXIT_FAILURE;
}
