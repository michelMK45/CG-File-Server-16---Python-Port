function BatchSleUpdate(idx)
	local as = gSportsRNA
	local state = as:GetTable("wvBatchSle", idx)

	db.batchsle[idx].lightType = as:GetInt(state, "stadLightType")
	db.batchsle[idx].stadiumID = as:GetInt(state, "stadID")
	db.batchsle[idx].prefix = "stadium" --as:GetString(state, "stadNamePrefix")
	
	
	local stadium = as:GetTable("wvStadium", 1)
	
	db.batchsle[idx].homeTeamIDasset = as:GetInt(stadium, "homeKitTeamID" )
	db.batchsle[idx].envLighting = as:GetInt(state, "wvAttribEnvLighting")
	
	local wipe3d = as:GetTable("wvWipe", 1)
	
	db.batchsle[idx].tournID = as:GetInt(wipe3d, "leagueID")
	db.batchsle[idx].tournID = getTournamentGraphics(db.batchsle[idx].tournID)
	
end

function BatchSleAssetBind(batchsle)
	local gr = gRenderables
   	local lod = 0

	gr:AddCallback(batchsle, lod, "BatchSleUpdate(?)")
	gr:AddAsset(batchsle, lod, "stadium", "${GetRMStadModelSle(?)}data/sceneassets/stadium/${db.batchsle[?].prefix}_${db.batchsle[?].stadiumID}.rx3")

	return batchsle
end

function GetRMStadModelSle(idx)
	local stad = ""
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.batchsle[idx].stadiumID.."_"..db.batchsle[idx].lightType.."_"..db.batchsle[idx].homeTeamIDasset.."_"..db.batchsle[idx].tournID..".rx3;"
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.batchsle[idx].stadiumID.."_0_"..db.batchsle[idx].homeTeamIDasset.."_"..db.batchsle[idx].tournID..".rx3;"
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.batchsle[idx].stadiumID.."_"..db.batchsle[idx].lightType.."_0_"..db.batchsle[idx].tournID..".rx3;"
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.batchsle[idx].stadiumID.."_0_0_"..db.batchsle[idx].tournID..".rx3;"
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.batchsle[idx].stadiumID.."_"..db.batchsle[idx].lightType.."_"..db.batchsle[idx].homeTeamIDasset.."_0.rx3;"
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.batchsle[idx].stadiumID.."_0_"..db.batchsle[idx].homeTeamIDasset.."_0.rx3;"
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.batchsle[idx].stadiumID.."_"..db.batchsle[idx].envLighting.."_0_0.rx3;"
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.batchsle[idx].stadiumID.."_"..db.batchsle[idx].lightType.."_0_0.rx3;"
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.batchsle[idx].stadiumID.."_0_0_0.rx3;"
	return stad
end

--Revolution Mod 16 V1.3.5
--Edited by scouser09