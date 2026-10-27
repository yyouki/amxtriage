/*
 * amxtriage SA-MP/open.mp filterscript bridge.
 *
 * Reads append-only records written by:
 *   amxtriage watch server_log.txt --alert-pawn-file scriptfiles/amxtriage-alerts.txt
 *
 * Security/performance defaults:
 * - only RCON administrators receive messages;
 * - reads at most 5 records per 1-second tick;
 * - ignores malformed records and overlong lines;
 * - accepts only a fixed record schema and numeric line/count fields;
 * - preserves encoded braces from untrusted text, so log content cannot inject color tags;
 * - starts at EOF to avoid replaying old alerts.
 *
 * Compile with the Pawn compiler and SA-MP/open.mp standard includes installed for your server.
 */

#define _console_included
#include <a_samp>

#define AMXTRIAGE_ALERT_FILE "amxtriage-alerts.txt"
#define AMXTRIAGE_POLL_MS (1000)
#define AMXTRIAGE_MAX_RECORDS_PER_TICK (5)
#define AMXTRIAGE_MAX_RECORD_BYTES (4096)
#define AMXTRIAGE_BUFFER_SIZE (8192)
#define AMXTRIAGE_FIELD_SIZE (512)
#define AMXTRIAGE_FIELD_COUNT (8)
#define AMXTRIAGE_CHAT_SIZE (144)
#define AMXTRIAGE_SAFE_CHAT_SIZE (288)

new g_AmxTriageReadOffset = 0;
new g_AmxTriageTimer = 0;
new g_AmxTriageLine[AMXTRIAGE_BUFFER_SIZE];
new g_AmxTriageFields[AMXTRIAGE_FIELD_COUNT][AMXTRIAGE_FIELD_SIZE];

forward AmxTriagePollAlerts();
forward bool:SplitAlertRecord(const source[], fields[AMXTRIAGE_FIELD_COUNT][AMXTRIAGE_FIELD_SIZE]);
forward bool:IsValidSeverity(const value[]);
forward bool:IsUnsignedDecimal(const value[], maxDigits);
forward bool:IsAmxTriageAdmin(playerid);

public OnFilterScriptInit()
{
    new File:handle = fopen(AMXTRIAGE_ALERT_FILE, io_read);
    if (handle)
    {
        // Do not send old alerts when the filterscript starts.
        g_AmxTriageReadOffset = flength(handle);
        fclose(handle);
    }
    else
    {
        // The Python watcher may create the file later.
        g_AmxTriageReadOffset = 0;
        print("[amxtriage] waiting for scriptfiles/amxtriage-alerts.txt");
    }

    new pollCallback[] = "AmxTriagePollAlerts";
    g_AmxTriageTimer = SetTimer(pollCallback, AMXTRIAGE_POLL_MS, true);
    if (!g_AmxTriageTimer)
    {
        print("[amxtriage] ERROR: failed to start alert polling timer");
        return 0;
    }

    print("[amxtriage] local alert bridge started; recipients: RCON admins only");
    return 1;
}

public OnFilterScriptExit()
{
    if (g_AmxTriageTimer)
    {
        KillTimer(g_AmxTriageTimer);
        g_AmxTriageTimer = 0;
    }
    return 1;
}

public AmxTriagePollAlerts()
{
    new File:handle = fopen(AMXTRIAGE_ALERT_FILE, io_read);
    if (!handle)
    {
        // Missing or temporarily unavailable export file must not stop the game server.
        return 1;
    }

    new fileLength = flength(handle);
    if (fileLength < g_AmxTriageReadOffset)
    {
        // The file was truncated. Start at its current end instead of replaying old content.
        g_AmxTriageReadOffset = fileLength;
    }

    if (fseek(handle, g_AmxTriageReadOffset, seek_start) < 0)
    {
        fclose(handle);
        return 1;
    }

    new processed = 0;
    while (processed < AMXTRIAGE_MAX_RECORDS_PER_TICK)
    {
        new recordStart = g_AmxTriageReadOffset;
        new readLength = fread(handle, g_AmxTriageLine, sizeof(g_AmxTriageLine));
        if (readLength <= 0)
        {
            break;
        }

        new rawLength = strlen(g_AmxTriageLine);
        if (recordStart + rawLength >= fileLength)
        {
            // fread returns a line without its newline. A line that reaches EOF without
            // a trailing newline may still be being appended; retry it on the next poll.
            g_AmxTriageReadOffset = recordStart;
            break;
        }

        new recordEnd = recordStart + rawLength + 1;
        StripLineEnding(g_AmxTriageLine);

        if (rawLength >= AMXTRIAGE_MAX_RECORD_BYTES)
        {
            // The producer caps each serialized row; ignore malformed oversized rows.
            g_AmxTriageReadOffset = recordEnd;
            processed++;
            continue;
        }

        if (!SplitAlertRecord(g_AmxTriageLine, g_AmxTriageFields))
        {
            // A malformed complete row is discarded, never executed.
            g_AmxTriageReadOffset = recordEnd;
            processed++;
            continue;
        }

        g_AmxTriageReadOffset = recordEnd;
        SendAdminAlert(g_AmxTriageFields);
        processed++;
    }

    fclose(handle);
    return 1;
}

stock StripLineEnding(line[])
{
    new length = strlen(line);
    while (length > 0 && (line[length - 1] == '\r' || line[length - 1] == '\n'))
    {
        line[--length] = EOS;
    }
    return 1;
}

stock bool:SplitAlertRecord(const source[], fields[AMXTRIAGE_FIELD_COUNT][AMXTRIAGE_FIELD_SIZE])
{
    new start = 0;
    new length = strlen(source);

    // Split the first seven separators; encoded fields cannot contain a literal pipe.
    for (new field = 0; field < AMXTRIAGE_FIELD_COUNT - 1; field++)
    {
        new delimiter = strfind(source, "|", false, start);
        if (delimiter < 0 || delimiter - start >= AMXTRIAGE_FIELD_SIZE)
        {
            return false;
        }

        strmid(fields[field], source, start, delimiter, AMXTRIAGE_FIELD_SIZE);
        start = delimiter + 1;
    }

    if (length - start >= AMXTRIAGE_FIELD_SIZE)
    {
        return false;
    }
    strmid(fields[AMXTRIAGE_FIELD_COUNT - 1], source, start, length, AMXTRIAGE_FIELD_SIZE);

    if (strfind(fields[AMXTRIAGE_FIELD_COUNT - 1], "|") != -1)
    {
        return false;
    }
    if (strcmp(fields[0], "AMXTRIAGE1") != 0 || strcmp(fields[7], "END") != 0)
    {
        return false;
    }
    if (!IsValidSeverity(fields[1]))
    {
        return false;
    }
    if (!IsUnsignedDecimal(fields[4], 10) || !IsUnsignedDecimal(fields[6], 10))
    {
        return false;
    }
    return true;
}

stock bool:IsValidSeverity(const value[])
{
    return strcmp(value, "CRITICAL") == 0
        || strcmp(value, "HIGH") == 0
        || strcmp(value, "MEDIUM") == 0
        || strcmp(value, "LOW") == 0;
}

stock bool:IsUnsignedDecimal(const value[], maxDigits)
{
    new length = strlen(value);
    if (length == 0 || length > maxDigits)
    {
        return false;
    }
    for (new index = 0; index < length; index++)
    {
        if (value[index] < '0' || value[index] > '9')
        {
            return false;
        }
    }
    return true;
}

stock DecodeBridgeField(const input[], output[], maxLength)
{
    new sourceIndex = 0;
    new targetIndex = 0;

    while (input[sourceIndex] != EOS && targetIndex < maxLength - 1)
    {
        if (input[sourceIndex] == '%' && input[sourceIndex + 1] == '2' && input[sourceIndex + 2] == '5')
        {
            output[targetIndex++] = '%';
            sourceIndex += 3;
        }
        else if (input[sourceIndex] == '%' && input[sourceIndex + 1] == '7' && input[sourceIndex + 2] == 'C')
        {
            output[targetIndex++] = '|';
            sourceIndex += 3;
        }
        else
        {
            // In particular, %7B/%7D remain encoded and cannot form inline color tags.
            output[targetIndex++] = input[sourceIndex++];
        }
    }
    output[targetIndex] = EOS;
    return targetIndex;
}

stock CopyShort(const source[], target[], maxLength)
{
    format(target, maxLength, "%s", source);
    return 1;
}

stock CopyTail(const source[], target[], maxLength)
{
    new length = strlen(source);
    if (length < maxLength)
    {
        format(target, maxLength, "%s", source);
        return 1;
    }

    new tail[64];
    new take = maxLength - 4;
    if (take >= sizeof(tail))
    {
        take = sizeof(tail) - 1;
    }
    strmid(tail, source, length - take, length, sizeof(tail));
    format(target, maxLength, "...%s", tail);
    return 1;
}

stock EscapeFormatPercents(const input[], output[], maxLength)
{
    new sourceIndex = 0;
    new targetIndex = 0;
    while (input[sourceIndex] != EOS && targetIndex < maxLength - 1)
    {
        if (input[sourceIndex] == '%')
        {
            if (targetIndex + 2 >= maxLength)
            {
                break;
            }
            output[targetIndex++] = '%';
            output[targetIndex++] = '%';
            sourceIndex++;
        }
        else
        {
            output[targetIndex++] = input[sourceIndex++];
        }
    }
    output[targetIndex] = EOS;
    return targetIndex;
}

stock SendAdminAlert(fields[AMXTRIAGE_FIELD_COUNT][AMXTRIAGE_FIELD_SIZE])
{
    new prefixRaw[AMXTRIAGE_FIELD_SIZE];
    new fileRaw[AMXTRIAGE_FIELD_SIZE];
    new messageRaw[AMXTRIAGE_FIELD_SIZE];
    new prefix[13];
    new file[40];
    new lineText[16];
    new message[AMXTRIAGE_FIELD_SIZE];
    new messageWithCount[AMXTRIAGE_FIELD_SIZE];
    new output[AMXTRIAGE_CHAT_SIZE];
    new safeOutput[AMXTRIAGE_SAFE_CHAT_SIZE];

    DecodeBridgeField(fields[2], prefixRaw, sizeof(prefixRaw));
    DecodeBridgeField(fields[3], fileRaw, sizeof(fileRaw));
    DecodeBridgeField(fields[5], messageRaw, sizeof(messageRaw));

    // Keep the location readable within the game's 144-character chat limit.
    CopyShort(prefixRaw, prefix, sizeof(prefix));
    CopyTail(fileRaw, file, sizeof(file));
    if (strval(fields[4]) <= 0)
    {
        format(lineText, sizeof(lineText), "?");
    }
    else
    {
        format(lineText, sizeof(lineText), "%s", fields[4]);
    }
    CopyShort(messageRaw, message, sizeof(message));

    if (strval(fields[6]) > 1)
    {
        format(messageWithCount, sizeof(messageWithCount), "%s (x%s)", message, fields[6]);
    }
    else
    {
        format(messageWithCount, sizeof(messageWithCount), "%s", message);
    }

    format(
        output,
        sizeof(output),
        "{FFFFFF}[%s] [%s] {FF0000}%s{FFFFFF}:{0000FF}%s{FFFFFF} - %s",
        prefix,
        fields[1],
        file,
        lineText,
        messageWithCount
    );

    // open.mp/SA-MP interprets format specifiers in chat strings; escape '%' from log text.
    EscapeFormatPercents(output, safeOutput, sizeof(safeOutput));

    for (new playerid = 0; playerid < MAX_PLAYERS; playerid++)
    {
        if (IsPlayerConnected(playerid) && IsAmxTriageAdmin(playerid))
        {
            SendClientMessage(playerid, 0xFFFFFFFF, safeOutput);
        }
    }
    return 1;
}

stock bool:IsAmxTriageAdmin(playerid)
{
    // Default policy: only players authenticated as RCON administrators receive alerts.
    // Owners using another ACL must replace this function with their server's trusted check.
    return IsPlayerAdmin(playerid) != 0;
}
