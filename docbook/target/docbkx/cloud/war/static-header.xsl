<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
	xmlns="http://www.w3.org/1999/xhtml"
	xmlns:h="http://www.w3.org/1999/xhtml"
	xmlns:f="http://docbook.org/xslt/ns/extension"
	xmlns:t="http://docbook.org/xslt/ns/template"
	xmlns:m="http://docbook.org/xslt/ns/mode"
	xmlns:fn="http://www.w3.org/2005/xpath-functions"
	xmlns:ghost="http://docbook.org/ns/docbook/ephemeral"
	xmlns:db="http://docbook.org/ns/docbook"
	exclude-result-prefixes="h f m fn db t ghost"
	version="2.0">
	
	<xsl:template name="static-header">
		
		<div id="page-darken-wrap">&#160;</div>
		<div id="page-wrap">
			<div id="ceiling-wrap">
				<div class="container_12" id="pocket-container">
					<div id="pocket-wrap">
						<div id="pocket-livechat" class="pocketitem">
							<div class="icon">&#160;</div>
							<div class="content" onclick="track_chat_button('Home: Header: Live Chat');launchChatWindow('39941')">
								<span class="pocketitem-gray">Live Chat</span>
							</div>
						</div>
						<div id="pocket-salesnumber" class="pocketitem">
							<div class="icon">&#160;</div>
							<div class="content">
								<span class="pocketitem-gray">Sales:</span> 1-800-961-2888
							</div>
						</div>
						<div id="pocket-supportnumber" class="pocketitem">
							<a href="/support/"></a>
							<div class="icon">&#160;</div>
							<div class="content">
								<a href="/support/"><span class="pocketitem-gray">Support:</span></a> 1-800-961-4454
							</div>
						</div>
						<div class="clear">&#160;</div>
					</div>
					<div id="navigation-wrap">
						<div id="logo-wrap" onclick="getURL('/')">&#160;</div>
						<div id="menu-wrap">
							<div class='menuoption' id='menuoption-hostingsolutions'>
								<a href="/hosting_solutions/" class="menuoption menuoption-off">Getting Started</a>
								<div class='menu' id='menu-hostingsolutions'>
									<div class='container_12'>
										<div class='navigation_1'>
											<div class='menu-title'>
												Hosting Solutions
											</div><br />
											<br />
										</div>
										<div class='navigation_2'>
											<ul class='navigation'>
												<li class='heading-link'>
													<a href="/hosting_solutions/">Solutions</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/hosting_solutions/websites/">Corporate Websites</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/hosting_solutions/customapps/">Custom Applications</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/hosting_solutions/ecommerce/">E-commerce Websites</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/hosting_solutions/richmedia/">Rich Media Websites</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/hosting_solutions/saas/">SaaS Applications</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/hosting_solutions/testdev/">Test &amp; Development Environments</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/enterprise_hosting/">Enterprise Business Solutions</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/enterprise_hosting/advisory_services/">Advisory Services</a>
													<div class='clear'>&#160;</div>
												</li>
											</ul>
										</div>
										<div class='grid_divider_vertical'>&#160;</div>
										<div class='navigation_2'>
											<ul class='navigation'>
												<li class='heading-link'>
													<a href="/hosting_solutions/">Technologies</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloud/">Cloud Hosting</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/cloud/cloud_hosting_products/servers/">Cloud Servers™</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/cloud/managed_cloud/">Cloud Servers™ - Managed</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/cloud/cloud_hosting_products/sites/">Cloud Sites™</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/cloud/cloud_hosting_products/loadbalancers/">Cloud Load Balancers</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/cloud/cloud_hosting_products/files/">Cloud Files™</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/cloud/cloud_hosting_products/monitoring/">Cloud Monitoring</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/cloud/cloud_hosting_products/dns/">Cloud DNS</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/cloud/private_edition/">Cloud Private Edition</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/managed_hosting/">Managed Hosting</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/managed_hosting/configurations/">Managed Server Configurations</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/managed_hosting/private_cloud/">Private Clouds</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/managed_hosting/managed_colocation/">Managed Colocation Servers</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/managed_hosting/services/proservices/criticalsites/">Rackspace Critical Sites</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/hosting_solutions/hybrid_hosting/">Hybrid Hosting</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/hosting_solutions/hybrid_hosting/rackconnect/">RackConnect™</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/apps">Email &amp; Apps</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/apps/email_hosting/rackspace_email/">Rackspace Email</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/apps/email_hosting/exchange_hosting/">Microsoft Exchange</a>
													<div class='clear'>&#160;</div>
												</li>
												<li style="list-style: none">/
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/apps/file_sharing/">File Sharing</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/apps/backup_and_collaboration/">Backup &amp; Collaboration</a>
													<div class='clear'>&#160;</div>
												</li>
											</ul>
										</div>
										<div class='grid_divider_vertical'>&#160;</div>
										<div class='navigation_2'>
											<ul class='navigation'>
												<li class='heading-link'>
													<a href="/cloud/private_edition/">Cloud Builders</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloud/private_edition/">Cloud Private Edition</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloud/private_edition/openstack/">About OpenStack™</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloud/private_edition/training/">Rackspace Training</a>
													<div class='clear'>&#160;</div>
												</li>
											</ul>
										</div>
										<div class='clear'>&#160;</div>
									</div>
								</div>
							</div>
							<div class='menuoption' id='menuoption-cloud'>
								<a href="/cloud/" class="menuoption menuoption-off">API Documentation</a>
								<div class='menu' id='menu-cloud'>
									<div class='container_12'>
										<div class='navigation_1'>
											<div class='menu-title'>
												Cloud Hosting
											</div><br />
											<br />
											<div class='rsOrderButton horizontal' url='https://cart.rackspace.com/cloud/'>
												Order Now
											</div>
											<div class='rsSupport' onclick='getURL("/support/")'>
												Help &amp; Support
											</div>
										</div>
										<div class='navigation_2'>
											<ul class='navigation'>
												<li class='heading-link'>
													<a href="/cloud/cloud_hosting_products/">Cloud Products</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloud/cloud_hosting_products/">Overview</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloud/cloud_hosting_products/servers/">Cloud Servers™</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloud/managed_cloud/">Cloud Servers™ - Managed</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloud/cloud_hosting_products/sites/">Cloud Sites™</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloud/cloud_hosting_products/loadbalancers/">Cloud Load Balancers</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloud/cloud_hosting_products/files/">Cloud Files™</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloud/cloud_hosting_products/monitoring/">Cloud Monitoring</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloud/cloud_hosting_products/dns/">Cloud DNS</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloud/private_edition/">Cloud Private Edition</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='heading-link'>
													<a href="/cloudreseller/">Partner Program</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloudreseller/">Program Overview</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="https://affiliates.rackspacecloud.com/">Cloud Affiliates</a>
													<div class='clear'>&#160;</div>
												</li>
											</ul>
										</div>
										<div class='grid_divider_vertical'>&#160;</div>
										<div class='navigation_2'>
											<ul class='navigation'>
												<li class='heading-link'>
													<a href="/cloud/cloud_hosting_faq/">Learn More</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloud/cloud_hosting_faq/">Cloud FAQ</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloud/who_uses_cloud_computing/">Cloud Customers</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloud/what_is_cloud_computing/">Cloud Computing?</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/knowledge_center/cloudu/">Cloud University</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloud/cloud_hosting_demos/">Cloud Demos</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/knowledge_center/">Knowledge Center</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='heading-link'>
													<a href="/cloud/tools/">Cloud Tools</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
											</ul>
										</div>
										<div class='grid_divider_vertical'>&#160;</div>
										<div class='navigation_2'>
											<ul class='navigation'>
												<li class='heading-link'>
													<a href="/cloud/aboutus/story/">About</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloud/aboutus/story/">Our Story</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloud/aboutus/contact/">Contact Us</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/information/newsroom/">Media</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloud/aboutus/events/">Events</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="http://www.rackertalent.com/">Jobs</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/information/links/">Link to Us</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/cloud/legal/">Legal</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='heading-link'>
													<a href="/blog/channels/cloud-industry-insights/">Blog</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
											</ul>
										</div>
										<div class='clear'>&#160;</div>
									</div>
								</div>
							</div>
							<div class='menuoption' id='menuoption-managed'>
								<a href="/managed_hosting/" class="menuoption menuoption-off">Core Concepts</a>
								<div class='menu' id='menu-managed'>
									<div class='container_12'>
										<div class='navigation_1'>
											<div class='menu-title'>
												Managed Hosting
											</div><br />
											<br />
											<div class='rsOrderButton horizontal' url='/managed_hosting/configurations/'>
												Order Now
											</div>
											<div class='rsSupport' onclick='getURL("/support/")'>
												Help &amp; Support
											</div>
										</div>
										<div class='navigation_2'>
											<ul class='navigation'>
												<li class='heading-link'>
													<a href="/managed_hosting/">Managed Solutions</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/managed_hosting/private_cloud/">Managed Private Clouds</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/managed_hosting/managed_colocation/">Managed Colocation</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/managed_hosting/configurations/">Managed Server Configurations</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='heading-link'>
													<a href="/partners/">Partner Program</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
											</ul>
										</div>
										<div class='grid_divider_vertical'>&#160;</div>
										<div class='navigation_2'>
											<ul class='navigation'>
												<li class='heading-link'>
													<a href="/managed_hosting/dedicated_servers/">Compare Managed</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
												<li class='heading-link'>
													<a href="/managed_hosting/support/">Support Experience</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/managed_hosting/support/dedicatedteam/">Dedicated Support Teams</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/managed_hosting/support/promise/">The Fanatical Support Promise<sup>®</sup></a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/managed_hosting/support/customers/">Our Customers</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/managed_hosting/support/servicelevels/">Managed Service Levels</a>
													<div class='clear'>&#160;</div>
												</li>
											</ul>
										</div>
										<div class='grid_divider_vertical'>&#160;</div>
										<div class='navigation_2'>
											<ul class='navigation'>
												<li class='heading-link'>
													<a href="/managed_hosting/services/">Managed Services</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/managed_hosting/services/security/">Managed Security</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/managed_hosting/services/storage/">Managed Storage</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/managed_hosting/services/database/">Managed Databases</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/managed_hosting/services/proservices/sharepoint/">Dedicated Microsoft<sup>®</sup> SharePoint</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/managed_hosting/services/proservices/criticalsites/">Rackspace Critical Sites</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/managed_hosting/services/proservices/disasterrecovery/">Disaster Recovery Services</a>
													<div class='clear'>&#160;</div>
												</li>
											</ul>
										</div>
										<div class='clear'>&#160;</div>
									</div>
								</div>
							</div>
							<div class='menuoption' id='menuoption-email'>
								<a href="/apps" class="menuoption menuoption-off">Advanced Topics</a>
								<div class='menu' id='menu-email'>
									<div class='container_12'>
										<div class='navigation_1'>
											<div class='menu-title'>
												Email &amp; Apps
											</div><br />
											<br />
											<div class='rsOrderButton horizontal' url='https://cart.rackspace.com/apps/'>
												Free Trial
											</div>
											<div class='rsSupport' onclick='getURL("/apps/support/")'>
												Email Help &amp; Support
											</div>
										</div>
										<div class='navigation_2'>
											<ul class='navigation'>
												<li class='heading-link'>
													<a href="/apps">Our Apps</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/apps/email_hosting/">Email Hosting</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/apps/email_hosting/rackspace_email/">Rackspace Email</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/apps/email_hosting/exchange_hosting/">Microsoft Exchange</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/apps/email_hosting/exchange_hybrid/">Exchange Hybrid</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/apps/file_sharing/">File Sharing</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/apps/file_sharing/hosted_sharepoint/">Microsoft SharePoint</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/apps/backup_and_collaboration/">Backup &amp; Collaboration</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/apps/backup_and_collaboration/online_file_storage/">Rackspace Cloud Drive</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/apps/backup_and_collaboration/data_backup_software/">Rackspace Server Backup</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/apps/email_hosting/email_archiving/">Email Archiving</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='heading-label'>Admin Tools
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/apps/control_panel/">Control Panel</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/apps/email_hosting/migrations/">Migrations App</a>
													<div class='clear'>&#160;</div>
												</li>
											</ul>
										</div>
										<div class='grid_divider_vertical'>&#160;</div>
										<div class='navigation_2'>
											<ul class='navigation'>
												<li class='heading-label'>Mobile Options
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/apps/email_hosting/rackspace_email/on_your_mobile/">For Rackspace Email</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/apps/email_hosting/exchange_hosting/on_your_mobile/">For Microsoft Exchange</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='heading-label'>Email Extras
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/apps/email_hosting/compare/">Compare Products</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/apps/email_marketing_solutions/">Email Marketing</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='heading-link'>
													<a href="/apps/why_hosted_apps/">Why Rack Apps</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/apps/why_hosted_apps/">Top 10 Reasons</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/whyrackspace/support/">Fanatical Support</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/apps/email_industry_leadership/">History &amp; Expertise</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/apps/customers/">Customer Case Studies</a>
													<div class='clear'>&#160;</div>
												</li>
											</ul>
										</div>
										<div class='grid_divider_vertical'>&#160;</div>
										<div class='navigation_2'>
											<ul class='navigation'>
												<li class='heading-label'>Considering a Switch?
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/apps/email_hosting_service_planning_guide/">Get Your Business Ready</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/apps/email_provider/">Select Your Provider</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/apps/email_hosting/migrations/">Migrate Your Data</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='heading-link'>
													<a href="/information/contactus/" rel="nofollow">Connect With Us</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/information/contactus/" rel="nofollow">Contact Us</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="http://feedback.rackspacecloud.com">Product Feedback</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/apps/careers/">Careers</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='heading-link'>
													<a href="/partners/">Partner Program</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
												<li class='heading-link'>
													<a href="/apps/support/">Help &amp; Support</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
											</ul>
										</div>
										<div class='clear'>&#160;</div>
									</div>
								</div>
							</div>
							<div class='menuoption' id='menuoption-rackspace'>
								<a href="/" class="menuoption menuoption-off">Tools</a>
								<div class='menu' id='menu-rackspace'>
									<div class='container_12'>
										<div class='navigation_1'>
											<div class='menu-title'>
												About the Company
											</div><br />
											<br />
										</div>
										<div class='navigation_2'>
											<ul class='navigation'>
												<li class='heading-link'>
													<a href="/whyrackspace/">Why Rackspace</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/whyrackspace/support/">Fanatical Support®</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/whyrackspace/network/">Our Network</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/whyrackspace/network/datacenters/">Our Data Centers</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/whyrackspace/network/ipv6/">IPv6 Deployment &amp; Readiness</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/whyrackspace/expertise/">Awards &amp; Expertise</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='heading-link'>
													<a href="/partners/">Partner Program</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/partners/">Program Overview</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/forms/partnerapplication/">Partner Application</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="http://rackspacepartner.force.com/us">Partner Portal Login</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/partners/partnersearch/">Partner Locator</a>
													<div class='clear'>&#160;</div>
												</li>
											</ul>
										</div>
										<div class='grid_divider_vertical'>&#160;</div>
										<div class='navigation_2'>
											<ul class='navigation'>
												<li class='heading-link'>
													<a href="/information/">Information Center</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/information/aboutus/">About Rackspace</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/information/newsroom/">Rackspace Newsroom</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/information/contactus/" rel="nofollow">Contact Information</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/information/aboutus/">Leadership</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/information/hosting101/">Hosting 101</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/information/events/" rel="nofollow">Programs &amp; Events</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/startup/">Rackspace Startup Program</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/information/events/rackgivesback/" rel="nofollow">Rack Gives Back</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='sub'>
													<div class='arrow'>&#160;</div><a href="/information/events/briefingprogram/">Briefing Program</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="http://www.rackertalent.com">Careers</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="http://ir.rackspace.com/phoenix.zhtml?c=221673&amp;p=irol-irhome">Investors</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/information/legal/">Legal</a>
													<div class='clear'>&#160;</div>
												</li>
											</ul>
										</div>
										<div class='grid_divider_vertical'>&#160;</div>
										<div class='navigation_2'>
											<ul class='navigation'>
												<li class='heading-label'>Blog Community
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="/blog/">The Official Rackspace Blog</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="http://www.rackertalent.com">Racker Talent</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class=''>
													<a href="http://www.building43.com">Building 43</a>
													<div class='clear'>&#160;</div>
												</li>
												<li class='heading-link'>
													<a href="/knowledge_center/">Knowledge Center</a>
													<div class='arrow'>&#160;</div>
													<div class='clear'>&#160;</div>
												</li>
											</ul>
										</div>
										<div class='clear'>&#160;</div>
									</div>
								</div>
							</div>
						</div>
						<div id="search-wrap">
							<form id="sitesearch" name="sitesearch" action="/searchresults/" onsubmit="return submitSiteSearch()">
								<input type="text" name="q" id="search" value="Search" onclick="cleanSlate('search')" autocomplete="off" style="color:#CCCCCC" />
								<div id="search-button" class="inactive" onclick="submitForm('sitesearch')">&#160;</div>
							</form>
						</div>
					</div>
				</div>
			</div>
		</div>
		
	</xsl:template>
	
	<xsl:template name="static-footer">
		<div id="footer-wrap">
			<div id="fatfooter-wrap">
				<div class="container_12">
					<div class='fatfooter_1 push_0'>
						<div>
							<a href="/">Rackspace</a>
						</div>
						<ul>
							<li>
								<a href="/information/aboutus/" class="footer">About Rackspace Hosting</a>
							</li>
							<li>
								<a href="/whyrackspace/support/" class="footer">Fanatical Support®</a>
							</li>
							<li>
								<a href="/hosting_solutions/" class="footer">Hosting Solutions</a>
							</li>
							<li>
								<a href="/information/hosting101/" class="footer">Web Hosting 101</a>
							</li>
							<li>
								<a href="/partners/" class="footer">Hosting Partner Programs</a>
							</li>
							<li>
								<a href="/cloudbuilders/openstack/" class="footer">OpenStack™</a>
							</li>
						</ul>
					</div>
					<div class='fatfooter_1 push_1'>
						<div>
							<a href="/managed_hosting/">Managed Hosting</a>
						</div>
						<ul>
							<li>
								<a href="/managed_hosting/configurations/" class="footer">Managed Configurations</a>
							</li>
							<li>
								<a href="/managed_hosting/managed_colocation/" class="footer">Managed Colocation Servers</a>
							</li>
							<li>
								<a href="/managed_hosting/dedicated_servers/" class="footer">Dedicated Servers</a>
							</li>
							<li>
								<a href="/managed_hosting/support/customers/" class="footer">Managed Customers</a>
							</li>
							<li>
								<a href="https://my.rackspace.com" class="footer" rel="nofollow">MyRackspace® Portal</a>
							</li>
						</ul>
					</div>
					<div class='fatfooter_1 push_2'>
						<div>
							<a href="/cloud/">Cloud Hosting</a>
						</div>
						<ul>
							<li>
								<a href="/cloud/cloud_hosting_products/servers/" class="footer">Cloud Servers™</a>
							</li>
							<li>
								<a href="/cloud/cloud_hosting_products/sites/" class="footer">Cloud Sites™</a>
							</li>
							<li>
								<a href="/cloud/cloud_hosting_products/loadbalancers/" class="footer">Cloud Load Balancers</a>
							</li>
							<li>
								<a href="/cloud/cloud_hosting_products/files/" class="footer">Cloud Files™</a>
							</li>
							<li>
								<a href="/cloud/cloud_hosting_demos/" class="footer">Cloud Hosting Demos</a>
							</li>
							<li>
								<a href="https://manage.rackspacecloud.com/pages/Login.jsp" class="footer">Cloud Customer Portal</a>
							</li>
						</ul>
					</div>
					<div class='fatfooter_1 push_3'>
						<div>
							<a href="/apps/">Email &amp; Apps</a>
						</div>
						<ul>
							<li>
								<a href="/apps/email_hosting/" class="footer">Rackspace Email Hosting</a>
							</li>
							<li>
								<a href="/apps/email_hosting/exchange_hosting/" class="footer">Microsoft Hosted Exchange</a>
							</li>
							<li>
								<a href="/apps/email_hosting/compare/" class="footer">Compare Hosted Products</a>
							</li>
							<li>
								<a href="/apps/email_hosting/email_archiving/" class="footer">Email Archiving</a>
							</li>
							<li>
								<a href="http://apps.rackspace.com/" class="footer">Customer Log-in</a>
							</li>
						</ul>
					</div>
					<div class='grid_divider_vertical push_3'>&#160;</div>
					<div class='fatfooter_1 push_4'>
						<div>
							<a href="/information/contactus/" rel="nofollow">Contact Us</a>
						</div>
						<div>
							<a href=""></a>
						</div>
						<div class='column_1'>
							<div class="footerIcon salesIcon">&#160;</div><span style="color:#4F81A6;">Sales</span>
						</div>
						<div class='column_2'>
							1-800-961-2888
						</div>
						<div class='clear'>&#160;</div>
						<div class='column_1'>
							<a href="/support/"></a>
							<div class="footerIcon supportIcon">&#160;</div><span style="position:relative; color:#4F81A6;">Support</span>
						</div>
						<div class='column_2'>
							1-800-961-4454
						</div>
						<div class='clear'>&#160;</div><br />
						<div>
							<a href="/information/contactus/" rel="nofollow">Connect With Us</a>
						</div>
						<div>
							<a href=""></a>
						</div>
						<div class='social linkedin' onclick='getURLNewWindow("http://www.linkedin.com/company/rackspace-hosting/")'>&#160;</div>
						<div class='social facebook' onclick='getURLNewWindow("http://www.facebook.com/rackspacehost")'>&#160;</div>
						<div class='social twitter' onclick='getURLNewWindow("http://twitter.com/rackspace")'>&#160;</div>
						<div class='social linktous' onclick='getURLNewWindow("/information/links/")'>&#160;</div>
						<div class='social email' onclick='getURLNewWindow("/forms/contactsales/")'>&#160;</div>
						<div class='clear'>&#160;</div>
					</div>
					<div class='clear'>&#160;</div>
				</div>
				<div id="rackerpowered">&#160;</div>
			</div>
		</div>
		<div id="basement-wrap" class="basement-wrap-nosnap">
			©2012 Rackspace, US Inc. <span class='footerlink'><a href="/information/aboutus/" class="basement">About Rackspace</a></span> | <span class='footerlink'><a href="/whyrackspace/support/" class="basement">Fanatical Support®</a></span> | <span class='footerlink'><a href="/hosting_solutions/" class="basement">Hosting Solutions</a></span> | <span class='footerlink'><a href="http://ir.rackspace.com" class="basement">Investors</a></span> | <span class='footerlink'><a href="http://www.rackertalent.com" class="basement">Careers</a></span> | <span class='footerlink'><a href="/information/legal/privacystatement/" class="basement">Privacy Statement</a></span> | <span class='footerlink'><a href="/information/legal/websiteterms/" class="basement">Website Terms</a></span> | <span class='footerlink'><a href="/sitemap/" class="basement" rel="nofollow">Sitemap</a></span>
		</div>
		<script type="text/javascript" src="http://docs.rackspace.com/common/jquery/qtip/jquery.qtip.js"><!--jQuery plugin for  popups. -->
			$('a[title]').qtip({ style: { background:green, name: 'cream', tip: true } })
		</script>
		
	</xsl:template>
	
	
</xsl:stylesheet>