/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * PAM module for native OPD2413 face authentication via org.opd2413.Face1.
 * Keeps camera, GPU, and ONNX dependencies isolated inside opd2413-faced.
 */

#define PAM_SM_AUTH

#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <syslog.h>

#include <security/pam_ext.h>
#include <security/pam_modules.h>
#include <systemd/sd-bus.h>

#define FACE_BUS_NAME  "org.opd2413.Face1"
#define FACE_BUS_PATH  "/org/opd2413/Face1"
#define FACE_BUS_IFACE "org.opd2413.Face1"

struct pam_opts {
	uint32_t timeout_ms;
	bool quiet;
	bool debug;
};

static void parse_args(int argc, const char **argv, struct pam_opts *opts)
{
	opts->timeout_ms = 3500;
	opts->quiet = false;
	opts->debug = false;

	for (int i = 0; i < argc; i++) {
		if (strncmp(argv[i], "timeout=", 8) == 0) {
			unsigned long v = strtoul(argv[i] + 8, NULL, 10);
			if (v >= 500 && v <= 30000)
				opts->timeout_ms = (uint32_t)v;
		} else if (strcmp(argv[i], "quiet") == 0) {
			opts->quiet = true;
		} else if (strcmp(argv[i], "debug") == 0) {
			opts->debug = true;
		}
	}
}

static bool has_nonempty_env(pam_handle_t *pamh, const char *name)
{
	const char *v = pam_getenv(pamh, name);
	if (v && v[0] != '\0')
		return true;
	v = getenv(name);
	return v && v[0] != '\0';
}

static bool is_remote_session(pam_handle_t *pamh)
{
	const char *rhost = NULL;
	if (pam_get_item(pamh, PAM_RHOST, (const void **)&rhost) == PAM_SUCCESS &&
	    rhost && rhost[0] != '\0')
		return true;

	return has_nonempty_env(pamh, "SSH_CONNECTION") ||
	       has_nonempty_env(pamh, "SSH_CLIENT") ||
	       has_nonempty_env(pamh, "SSH_TTY");
}

static int bus_query_user_bool(sd_bus *bus, const char *method, const char *user,
			       bool *out)
{
	sd_bus_error error = SD_BUS_ERROR_NULL;
	sd_bus_message *call = NULL;
	sd_bus_message *reply = NULL;
	int val = 0;
	int r;

	*out = false;
	r = sd_bus_message_new_method_call(bus, &call, FACE_BUS_NAME,
					   FACE_BUS_PATH, FACE_BUS_IFACE,
					   method);
	if (r < 0)
		goto out;

	r = sd_bus_message_append(call, "s", user);
	if (r < 0)
		goto out;

	r = sd_bus_call(bus, call, 800ULL * 1000ULL, &error, &reply);
	if (r < 0)
		goto out;

	r = sd_bus_message_read(reply, "b", &val);
	if (r >= 0)
		*out = (val != 0);

out:
	sd_bus_error_free(&error);
	sd_bus_message_unref(call);
	sd_bus_message_unref(reply);
	return r;
}

static int bus_verify(sd_bus *bus, const char *user, const char *service,
		      uint32_t timeout_ms, bool *matched, char *reason,
		      size_t reason_len)
{
	sd_bus_error error = SD_BUS_ERROR_NULL;
	sd_bus_message *call = NULL;
	sd_bus_message *reply = NULL;
	const char *rstr = "";
	double score = 0.0;
	int val = 0;
	int r;

	*matched = false;
	if (reason && reason_len > 0)
		reason[0] = '\0';

	r = sd_bus_message_new_method_call(bus, &call, FACE_BUS_NAME,
					   FACE_BUS_PATH, FACE_BUS_IFACE,
					   "Verify");
	if (r < 0)
		goto out;

	r = sd_bus_message_append(call, "ssu", user, service, timeout_ms);
	if (r < 0)
		goto out;

	const uint64_t dbus_timeout = ((uint64_t)timeout_ms + 6000ULL) * 1000ULL;
	r = sd_bus_call(bus, call, dbus_timeout, &error, &reply);
	if (r < 0) {
		if (reason && reason_len > 0)
			snprintf(reason, reason_len, "%s",
				 error.message ? error.message : strerror(-r));
		goto out;
	}

	r = sd_bus_message_read(reply, "bsd", &val, &rstr, &score);
	if (r >= 0) {
		*matched = (val != 0);
		if (reason && reason_len > 0 && rstr)
			snprintf(reason, reason_len, "%s", rstr);
	}

out:
	sd_bus_error_free(&error);
	sd_bus_message_unref(call);
	sd_bus_message_unref(reply);
	return r;
}

PAM_EXTERN int pam_sm_authenticate(pam_handle_t *pamh, int flags,
				   int argc, const char **argv)
{
	struct pam_opts opts;
	const char *user = NULL;
	const char *service = "unknown";
	sd_bus *bus = NULL;
	bool enrolled = false;
	bool matched = false;
	char reason[128] = { 0 };
	int r;

	parse_args(argc, argv, &opts);
	if (flags & PAM_SILENT)
		opts.quiet = true;

	if (is_remote_session(pamh))
		return PAM_IGNORE;

	if (pam_get_user(pamh, &user, NULL) != PAM_SUCCESS ||
	    !user || user[0] == '\0')
		return PAM_USER_UNKNOWN;

	if (pam_get_item(pamh, PAM_SERVICE, (const void **)&service) != PAM_SUCCESS ||
	    !service || service[0] == '\0')
		service = "unknown";

	r = sd_bus_open_system(&bus);
	if (r < 0) {
		if (opts.debug)
			pam_syslog(pamh, LOG_DEBUG, "sd_bus_open_system failed: %s",
				   strerror(-r));
		return PAM_IGNORE;
	}

	r = bus_query_user_bool(bus, "HasEnrolled", user, &enrolled);
	if (r < 0 || !enrolled) {
		if (opts.debug && r < 0)
			pam_syslog(pamh, LOG_DEBUG, "HasEnrolled failed: %s",
				   strerror(-r));
		sd_bus_flush_close_unref(bus);
		return PAM_IGNORE;
	}

	const bool is_polkit = (strcmp(service, "polkit-1") == 0);
	if (is_polkit) {
		bool polkit_armed = false;
		r = bus_query_user_bool(bus, "IsPolkitArmed", user, &polkit_armed);
		if (r < 0 || !polkit_armed) {
			if (opts.debug && r < 0)
				pam_syslog(pamh, LOG_DEBUG, "IsPolkitArmed failed: %s",
					   strerror(-r));
			sd_bus_flush_close_unref(bus);
			return PAM_IGNORE;
		}
	}

	if (!opts.quiet && !is_polkit)
		pam_info(pamh, "Verifying face...");

	r = bus_verify(bus, user, service, opts.timeout_ms,
		       &matched, reason, sizeof(reason));
	sd_bus_flush_close_unref(bus);

	if (r < 0) {
		pam_syslog(pamh, LOG_NOTICE, "Face verify error for %s (%s): %s",
			   user, service, reason[0] ? reason : strerror(-r));
		return PAM_AUTHINFO_UNAVAIL;
	}

	if (matched) {
		pam_syslog(pamh, LOG_INFO, "Face authenticated user %s (%s)",
			   user, service);
		return PAM_SUCCESS;
	}

	if (opts.debug)
		pam_syslog(pamh, LOG_DEBUG, "Face not matched for %s (%s): %s",
			   user, service, reason);

	if (strcmp(reason, "polkit-unarmed") == 0)
		return PAM_IGNORE;

	if (strcmp(reason, "not-enrolled") == 0)
		return PAM_AUTHINFO_UNAVAIL;

	return PAM_AUTH_ERR;
}

PAM_EXTERN int pam_sm_setcred(pam_handle_t *pamh, int flags,
			      int argc, const char **argv)
{
	(void)pamh;
	(void)flags;
	(void)argc;
	(void)argv;
	return PAM_SUCCESS;
}
