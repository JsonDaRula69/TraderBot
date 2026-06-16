> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Organizations and Projects

An **organization** is the top-level administrative entity in a Voyage account, with each account starting with a default organization. Billing, budget limits, and data controls are managed at the organization level. Rate limits and API keys are also managed at this level but can be further constrained within **projects**, which are sub-groupings of resources and settings often tied to a specific team or use case. An organization can contain multiple projects.

This guide will show you how to manage your organization and projects. All walkthroughs in this guide are done in the Voyage [dashboard](https://dash.voyageai.com/).

# What are the different user roles within organizations and projects, and what permissions do they entail?

Organizations have two roles: **Admin** and **Member**. Admins have full control of and access to their organizations, while Members have more limited permissions. Admins can create and manage projects, invite members, and assign roles. They are also automatically included in all projects within their organization.

Within projects, Admins can designate members as project **Owners**, who have full control and access within their projects. A summary of these roles is provided in the table below.

| Role   | Scope                    | Description                                                                                                                                                                                                                                                                                                                                                                                                      |
| ------ | ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Admin  | Organization             | Full control of and access to the organization and can:<br /><br />- Manage all billing information and controls<br />- Invite, remove, and manage all members<br />- Create, view, and archive all projects<br />- Create, revoke, and manage all API keys<br />- Manage all rate limits<br />- Manage all budget limits<br />- Manage all permissions to view usage information for others in the organization |
| Owner  | Project                  | Full control of and access to the project and can:<br /><br />- Invite, remove, and manage all project members<br />- Create, revoke, and manage all project API keys<br />- Manage project rate limits<br />- Manage project budget limits                                                                                                                                                                      |
| Member | Organization and Project | Can create keys for projects they are members of. Can view created API keys and keys within projects they are Owners of. Has view-only access to all other entities. Can leave organization or project.                                                                                                                                                                                                          |

## Granular Role Permissions

The following table details granular permissions for organization and project roles.

|                       | Org Admin   | Project Owner                                                                 | Member                                                                        |
| :-------------------- | :---------- | :---------------------------------------------------------------------------- | :---------------------------------------------------------------------------- |
| Org Usage / Costs     | Full access | View only or no access\*                                                      | View only or no access\*                                                      |
| Org API Keys          | Full access | Access to created keys and keys within owned projects.                        | Access to created keys                                                        |
| Org Members           | Full access | View only admins, owners, and members within the same project. Can leave org. | View only admins, owners, and members within the same project. Can leave org. |
| Org Manage Projects   | Full access | View only projects user is a member of.                                       | View only projects user is a member of.                                       |
| Org General           | Full access | View only                                                                     | View only                                                                     |
| Org Billing           | Full access | View only                                                                     | View only                                                                     |
| Org Rate Limits       | Full access | View only                                                                     | View only                                                                     |
| Org Budget Limits     | Full access | View only                                                                     | View only                                                                     |
| Org Data Control      | Full access | No access                                                                     | No access                                                                     |
| Org Terms of Service  | Full access | View only                                                                     | View only                                                                     |
| Project General       | Full access | View only                                                                     | View only                                                                     |
| Project Members       | Full access | Full access                                                                   | View only. Can leave project.                                                 |
| Project Usage         | Full access | Full access                                                                   | View only                                                                     |
| Project Budget Limits | Full access | Full access                                                                   | View only                                                                     |
| Project API Keys      | Full access | Full access                                                                   | Access to created keys                                                        |
| Project Rate Limits   | Full access | Full access                                                                   | View only                                                                     |

\* No access if organization Admin has set usage dashboard visibility to organization owners only.

# Can I belong to multiple organizations?

Yes, you can belong to multiple organizations. An admin from an organization must invite you. To switch between organizations, hover over your organization’s name in the top-left of the dashboard and select the organization from the list.

![Switch Organization](https://files.readme.io/302a75c78eaeafab5e86eecdc7ae1ef5c95ca5f2039c49d011eff43aacdf5094-switch-organization.png)

# How do I create a project?

You can create projects in two ways.

1. **Project selector.** Hover on the project name in the upper left-corner of the page and select **Add project**.

![Project Selector](https://files.readme.io/b6126080ef7f9434f324751b3410b994994a6ba7a41f5bab419544e39845b4eb-project-selector.png)

2. **Manage projects**. Navigate to the [**Manage Projects**](https://dashboard.voyageai.com/organization/projects) section under **Organization**. Click on the **Create** button in the upper right-corner of the page.

![Manage Projects](https://files.readme.io/a32c03276e15bf07b31ce7894c41420448ed7c2eee1a672bb62eca87cf26faf7-manage-projects.png)

Both options will launch a **Create a new project** modal. Provide a name and click the **Create** button.

![Create New Project Modal](https://files.readme.io/d5b230ffefac0d450fa0c5190ac221bb6c2021c701585bcd6a7f9a06b281aa8f-image.png)

# How can I add users to an organization and assign them to a project?

To add users to an organization, you must be an Admin. Navigate to the [**Members**](https://dashboard.voyageai.com/organization/members) section under **Organization** in the navigation sidebar. Click the **Invite** button in the upper-right corner to open the **Invite Team Members** modal.

![Members Section](https://files.readme.io/82c6fa304a890605bf3a1cdccf38e42fd1c47ec3e6287a389111b5f45fe6e805-image.png)

Enter the users' email addresses in the **Emails** field, assign their organization role using the **Role** dropdown, and select a project for them using the **Project** dropdown. Finally, click **Invite**. Invited users will receive an email to accept the invitation.

![Invite Team Members Modal](https://files.readme.io/518a111fc90d76526ded6228c9a16392506db973d2e7c65fadfa7143e74fcd82-image.png)