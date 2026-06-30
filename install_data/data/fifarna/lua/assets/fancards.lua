function FanCardsUpdate(idx)
	local as = gSportsRNA
	local fancards = as:GetTable("wvFanCards", idx)

	db.fancards[idx].homeTeamID = as:GetInt(fancards, "homeTeamID")
	db.fancards[idx].awayTeamID = as:GetInt(fancards, "awayTeamID")
	db.fancards[idx].stadiumID = as:GetInt(fancards, "stadID")
	db.fancards[idx].prefix = as:GetString(fancards, "stadNamePrefix")
	db.fancards[idx].lightID = as:GetInt(fancards, "lightID")
	
	local wipe3d = as:GetTable("wvWipe", 1)
	db.fancards[idx].tournamentID = as:GetInt(wipe3d, "leagueID")
	db.fancards[idx].tournamentID = getTournamentGraphics(db.fancards[idx].tournamentID)
end

function FanCardsAssetBind(fancards)
	local gr = gRenderables
   	local lod = 0

	gr:AddCallback(fancards, lod, "FanCardsUpdate(?)")
	gr:AddAsset(fancards, lod, "homePatchTexture", "${GetRMFancards(?,1)}data/ui/imgassets/crest/light/l${db.fancards[?].homeTeamID}.dds")
	gr:AddAsset(fancards, lod, "awayPatchTexture", "${GetRMFancards(?,2)}data/ui/imgassets/crest/light/l${db.fancards[?].awayTeamID}.dds")
	gr:AddAsset(fancards, lod, "tileTexture", "data/sceneassets/globaltex/globaltex_0.rx3")
	gr:AddAsset(fancards, lod, "stadium", "data/sceneassets/stadium/${db.fancards[?].prefix}_${db.fancards[?].stadiumID}.rx3")
	gr:AddAsset(fancards, lod, "charcmn", "data/sceneassets/charactercmn/charactercmn_${db.fancards[?].lightID}.rx3")
	return fancards
end

function GetRMFancards(idx,ven)
	local ban = ""
	
	local team = db.fancards[idx].homeTeamID
	local opp = db.fancards[idx].awayTeamID
	local var = math.random(0,3)
	
	if (ven == 2) then
	team = db.fancards[idx].awayTeamID
	opp = db.fancards[idx].homeTeamID
	end
	
	ban = ban.."data/ui/imgassets/crest/fancards/fancard_"..team.."_"..db.fancards[idx].tournamentID.."_"..opp.."_0.dds;"
	ban = ban.."data/ui/imgassets/crest/fancards/fancard_"..team.."_0_"..opp.."_0.dds;"
	ban = ban.."data/ui/imgassets/crest/fancards/fancard_"..team.."_"..db.fancards[idx].tournamentID.."_0_0.dds;"
	ban = ban.."data/ui/imgassets/crest/fancards/fancard_"..team.."_0_0_"..var..".dds;"
	ban = ban.."data/ui/imgassets/crest/fancards/fancard_"..team.."_0_0_0.dds;"
	return ban
end

--Revolution Mod 16 V1.0
--Edited by scouser09