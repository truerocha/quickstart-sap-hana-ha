import cfnresponse
import json
import boto3
import time
import sys

responseStr = {'Status' : {}}


def updateNetworkConfig(HANAInstanceID,HANAIPAddress,AWSRegion):
    CommandArray = []
    CommandArray.append('sed -i".bak" "/CLOUD_NETCONFIG_MANAGE/d" /etc/sysconfig/network/ifcfg-eth0')
    CommandArray.append('echo -e "CLOUD_NETCONFIG_MANAGE=\'no\'">> /etc/sysconfig/network/ifcfg-eth0')
    CommandArray.append('service network restart')
    CommandArray.append('service amazon-ssm-agent stop')
    CommandArray.append('service amazon-ssm-agent start')    
    CommandArray.append('echo "done"')
    CommentStr = 'Network config'
    InstanceIDArray =[HANAInstanceID]
    return executeSSMCommands(CommandArray,InstanceIDArray,CommentStr,AWSRegion)

def backupHANAonPrimary(HANAPrimaryInstanceID,hanaSID,hanaInstanceNo,HANAMasterPass,AWSRegion):
    CommandArray = []
    CommandArray.append('HANAVersion='+'`su - '+hanaSID.lower()+'adm -c "HDB version | grep version:"`')
    CommandArray.append('HANAVersion=`echo $HANAVersion | awk \'{print $2}\' |  awk -F\'.\' \'{print $1}\'`')
    CommandArray.append('if [[ $HANAVersion -ne 1 ]]')
    CommandArray.append('then')
    CommandArray.append('echo $HANAVersion')
    CommandArray.append('su - '+hanaSID.lower()+'adm -c "hdbsql -u system -i '+hanaInstanceNo+' -d SystemDB -p '+HANAMasterPass+' \\"BACKUP DATA FOR SystemDB  USING FILE (\'backupSystem\')\\""')    
    CommandArray.append('su - '+hanaSID.lower()+'adm -c "hdbsql -u system -i '+hanaInstanceNo+' -d SystemDB -p '+HANAMasterPass+' \\"BACKUP DATA FOR '+hanaSID+' USING FILE (\'backup'+hanaSID+'\')\\""')
    CommandArray.append('else')
    CommandArray.append('su - '+hanaSID.lower()+'adm -c "hdbsql -u system -i '+hanaInstanceNo+' -p '+HANAMasterPass+' \\"BACKUP DATA USING FILE (\'backupDatabase\')\\""')    
    CommandArray.append('fi')
    CommentStr = 'Backup Database on Primary'
    InstanceIDArray =[HANAPrimaryInstanceID]
    return executeSSMCommands(CommandArray,InstanceIDArray,CommentStr,AWSRegion)

def executeSSMCommands(CommandArray,InstanceIDArray,CommentStr,AWSRegion):
    session = boto3.Session()
    ssmClient = session.client('ssm', region_name=AWSRegion)
    ssmCommand = ssmClient.send_command(
                InstanceIds=InstanceIDArray,
                DocumentName='AWS-RunShellScript',
                TimeoutSeconds=30,
                Comment=CommentStr,
                Parameters={
                        'commands': CommandArray
                    }
                )
    L_SSMCommandID = ssmCommand['Command']['CommandId']
    status = 'Pending'
    while status == 'Pending' or status == 'InProgress':
        status = (ssmClient.list_commands(CommandId=L_SSMCommandID))['Commands'][0]['Status']
        time.sleep(3)

    if (status == "Success"):
        #response = ssmClient.list_command_invocations(CommandId=L_SSMCommandID,InstanceId=InstanceIDArray[0],Details=True)
        return 1
    else:
        return 0

def manageRetValue(retValue,FuncName,input, context):
    global responseStr
    if (retValue == 1):
        responseStr['Status'][FuncName] = "Success"
    else:
        responseStr['Status'][FuncName] = "Failed"
        cfnresponse.send(input, context, cfnresponse.FAILED, responseStr)
        sys.exit(0)


def lambda_handler(input, context):
    global responseStr
    try:
        if (input['RequestType'] == "Update") or (input['RequestType'] == "Create"):
            HANAPrimaryInstanceID = input['ResourceProperties']['PrimaryInstanceId']
            HANASecondaryInstanceID = input['ResourceProperties']['SecondaryInstanceId']
            AWSRegion = input['ResourceProperties']['AWSRegion']
            HANAPrimaryIPAddress = input['ResourceProperties']['HANAPrimaryIPAddress']
            HANASecondaryIPAddress = input['ResourceProperties']['HANASecondaryIPAddress']
            hanaSID = input['ResourceProperties']['SID']
            hanaInstanceNo = input['ResourceProperties']['InstanceNo']
            HANAMasterPass = input['ResourceProperties']['HANAMasterPass']

            retValue = updateNetworkConfig(HANAPrimaryInstanceID,HANAPrimaryIPAddress,AWSRegion)
            manageRetValue(retValue,"updateNetworkConfigPrimary",input, context)

            retValue = updateNetworkConfig(HANASecondaryInstanceID,HANASecondaryIPAddress,AWSRegion)
            manageRetValue(retValue,"updateNetworkConfigSecondary",input, context)

            retValue = backupHANAonPrimary(HANAPrimaryInstanceID,hanaSID,hanaInstanceNo,HANAMasterPass,AWSRegion)
            manageRetValue(retValue,"backupHANAonPrimary",input, context)

            cfnresponse.send(input, context, cfnresponse.SUCCESS, {'Status':json.dumps(responseStr)})
        else:
            responseStr['Status'] = 'Nothing to do as Request Type is : ' + input['RequestType']
            cfnresponse.send(input, context, cfnresponse.SUCCESS, {'Status':json.dumps(responseStr)})
    except Exception as e:
        responseStr['Status'] = str(e)
        cfnresponse.send(input, context, cfnresponse.FAILED, {'Status':json.dumps(responseStr)})