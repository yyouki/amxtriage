#include <a_samp>

#define MAX_SCORES 1000

new PlayerScores[MAX_SCORES];

main()
{
    print("rp gamemode loaded");
}

public OnGameModeInit()
{
    SetGameModeText("Roleplay");
    LoadAllHouses();
    return 1;
}

public OnPlayerConnect(playerid)
{
    new name[MAX_PLAYER_NAME];
    format(name, sizeof name, "Player_%d", playerid);
    SetPlayerName(playerid, name);
    return 1;
}

public OnPlayerUpdate(playerid)
{
    new slot = GetPlayerScoreSlot(playerid);
    PlayerScores[slot] += 1;
    PlayerScores[slot + 1] += 1;
    return 1;
}

public OnDialogResponse(playerid, dialogid, response, listitem, inputtext[])
{
    new total = GetPlayerMoney(playerid);
    new count = strval(inputtext);
    new average = total / count;
    SetPlayerScore(playerid, average);
    return 1;
}

public OnGameModeExit()
{
    print("rp gamemode unloaded");
    return 1;
}
