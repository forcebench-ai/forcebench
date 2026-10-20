@IsTest
private class FieldJobTriggerHandlerTest {
    @IsTest
    static void stampsTheSiteRegion() {
        Service_Site__c site = new Service_Site__c(Name = 'Depot', Region__c = 'West');
        insert as system site;
        Field_Job__c job = new Field_Job__c(Site__c = site.Id);
        insert as system job;
        Assert.areEqual(
            'West', [SELECT Job_Region__c FROM Field_Job__c WHERE Id = :job.Id WITH SYSTEM_MODE].Job_Region__c
        );
    }

    @IsTest
    static void flagsALateCompletion() {
        Field_Job__c job = new Field_Job__c(
            Priority_Band__c = 'P1', Stage__c = 'In Progress', Scheduled_Start__c = Datetime.now().addHours(-6)
        );
        insert as system job;
        job.Stage__c = 'Completed';
        job.Customer_Signoff__c = true;
        job.Signoff_Name__c = 'R. Ortiz';
        update as system job;
        Field_Job__c saved = [
            SELECT Completed_On__c, SLA_Breached__c FROM Field_Job__c WHERE Id = :job.Id WITH SYSTEM_MODE
        ];
        Assert.isNotNull(saved.Completed_On__c);
        Assert.isTrue(saved.SLA_Breached__c);
    }

    @IsTest
    static void refusesToReopen() {
        Field_Job__c job = new Field_Job__c(Stage__c = 'Completed', Customer_Signoff__c = true, Signoff_Name__c = 'A. Lee');
        insert as system job;
        job.Stage__c = 'In Progress';
        Database.SaveResult result = Database.update(job, false, AccessLevel.SYSTEM_MODE);
        Assert.isFalse(result.isSuccess());
    }
}
