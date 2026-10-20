/**
 * Before-save logic for field jobs (FieldJobTrigger). Runs after the Field Job Completion flow,
 * which has already stamped Completed_On__c when a job is completed.
 *
 * - Copies the site's region onto the job (Job_Region__c).
 * - Refuses to reopen a completed job.
 * - On completion, flags the job when it was completed later than its SLA allows
 *   (SLA_Policy__mdt: hours from the scheduled start, by priority band).
 */
public with sharing class FieldJobTriggerHandler {
    public static void beforeSave(List<Field_Job__c> jobs, Map<Id, Field_Job__c> oldJobs) {
        stampRegion(jobs, oldJobs);
        for (Field_Job__c job : jobs) {
            Field_Job__c old = oldJobs == null ? null : oldJobs.get(job.Id);
            if (old != null && old.Stage__c == 'Completed' && job.Stage__c != 'Completed') {
                job.addError('A completed job cannot be reopened.');
                continue;
            }
            if (job.Stage__c == 'Completed' && (old == null || old.Stage__c != 'Completed')) {
                job.SLA_Breached__c = breached(job);
            }
        }
    }

    private static void stampRegion(List<Field_Job__c> jobs, Map<Id, Field_Job__c> oldJobs) {
        Set<Id> siteIds = new Set<Id>();
        for (Field_Job__c job : jobs) {
            Field_Job__c old = oldJobs == null ? null : oldJobs.get(job.Id);
            if (job.Site__c != null && (old == null || old.Site__c != job.Site__c || job.Job_Region__c == null)) {
                siteIds.add(job.Site__c);
            }
        }
        if (siteIds.isEmpty()) {
            return;
        }
        Map<Id, Service_Site__c> sites = new Map<Id, Service_Site__c>(
            [SELECT Id, Region__c FROM Service_Site__c WHERE Id IN :siteIds WITH SYSTEM_MODE]
        );
        for (Field_Job__c job : jobs) {
            Service_Site__c site = sites.get(job.Site__c);
            if (site != null) {
                job.Job_Region__c = site.Region__c;
            }
        }
    }

    private static Boolean breached(Field_Job__c job) {
        if (job.Scheduled_Start__c == null || job.Completed_On__c == null || job.Priority_Band__c == null) {
            return false;
        }
        for (SLA_Policy__mdt policy : SLA_Policy__mdt.getAll().values()) {
            if (policy.Band__c == job.Priority_Band__c && policy.Resolution_Hours__c != null) {
                return job.Completed_On__c > job.Scheduled_Start__c.addHours(policy.Resolution_Hours__c.intValue());
            }
        }
        return false;
    }
}
