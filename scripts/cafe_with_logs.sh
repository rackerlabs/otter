#!/usr/bin/env bash

# Runs cafe with the arguments you give, pipes the output to TEE, parses the
# output for the log files, and move the log files to the specified directory

# Usage:  cafe_with_logs.sh <logdir to move to> <cafe args>

LOG_DIR=$1
OUTFILE="_tmp.out"
shift

echo "cafe-runner $*"
cafe-runner $* | tee ${OUTFILE}

CURR_LOGS=$(sed -ne "s/^Detailed logs: \(.*\)$/\1/p" ${OUTFILE})
mv ${CURR_LOGS} ${LOG_DIR}
rm ${OUTFILE}
