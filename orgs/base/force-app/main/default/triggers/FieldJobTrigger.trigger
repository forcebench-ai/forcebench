trigger FieldJobTrigger on Field_Job__c (before insert, before update) {
    FieldJobTriggerHandler.beforeSave(Trigger.new, Trigger.oldMap);
}
