uint32 TrialId;
int moveForward = 1;

fileHeaderV016onwards fHv016onwards;
fileHeaderV013onwards fHv013onwards;
fileHeaderV4to12 fH4to12;
fileHeaderV3 fH3;
fileHeaderV2 fH2;



uint32 readHeader(FILE *pFile, char format[])
{
    
    uint32 bytesRead, TrialId;
    if(strcmp(format,"V016")==0)
    {
        bytesRead = fread(&fHv016onwards,1,sizeof(fHv016onwards),pFile);
        TrialId = fHv016onwards.TrialId;
    }
    else if(strcmp(format,"V013")==0 | strcmp(format,"V014")==0 | strcmp(format,"V015")==0)
    {
        bytesRead = fread(&fHv013onwards,1,sizeof(fHv013onwards),pFile);
        TrialId = fHv013onwards.TrialId;
        
    }
    // If the file format is V4 or V11, then read header with CerebusId
    // and also the TaskName else Read it without.
    else if(strcmp(format,"V004")==0 || strcmp(format,"V011")==0 || strcmp(format,"V012")==0)
    {
        bytesRead = fread(&fH4to12,1,sizeof(fH4to12),pFile);
        TrialId = fH4to12.TrialId;
    }
    // V011 adds eye data etc
    else if(strcmp(format,"V003")==0)
    {
        bytesRead = fread(&fH3,1,sizeof(fH3),pFile);
        TrialId = fH3.TrialId;
    }
    else if(strcmp(format,"V002")==0)
    {
        bytesRead  = fread(&fH2,1,sizeof(fH2),pFile);
        //          numSamples = (fSize - sizeof(fH2))/sizeof(struct continuousData);
        TrialId = fH2.TrialId;
    }
    else
    {
        mexErrMsgIdAndTxt( "MATLAB:parseContinuousMex:badVersionNumber",
                "This header version is unsupported, check your inputs please \n");
        moveForward = 0;
    }
    return bytesRead;
    
}


uint32 checkFile(FILE *pFile)
{
    uint32 fSize;
    if(pFile == NULL){
        mexErrMsgIdAndTxt( "MATLAB:parseContinuousMex:fileOpenFailed",
                "Could not open file, check filename \n");
    }
    fseek (pFile , 0 , SEEK_END);
    fSize = ftell(pFile);
    rewind(pFile);
    return fSize;
    
}
