<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet exclude-result-prefixes="d g"
                xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:d="http://docbook.org/ns/docbook"
		            xmlns="http://www.w3.org/1999/xhtml"
								xmlns:g="http://www.google.com"
                version="1.1">

  <!-- <xsl:import href="urn:docbkx:stylesheet-orig/xsl/webhelp.xsl" /> -->
  <xsl:import href="webhelp.xsl" />
  <xsl:import href="titlepage.templates.xsl"/>
  <xsl:import href="changebars.xsl"/>
  <xsl:import href="graphics.xsl"/>
  <xsl:import href="../this.xsl"/>
  <xsl:param name="admon.graphics" select="1"></xsl:param>
  <xsl:param name="webhelp.war">0</xsl:param>
  <xsl:param name="docbook.infile"/>
  <xsl:param name="war.dirname"><xsl:value-of select="normalize-space(/processing-instruction('rax-warinfo'))"/></xsl:param>
  <xsl:param name="webhelp.common.dir">
    <xsl:choose>
      <xsl:when test="$webhelp.war != '0' and $webhelp.war != ''">/<xsl:value-of select="$war.dirname"/>/common/</xsl:when>
      <xsl:otherwise>../common/</xsl:otherwise>
    </xsl:choose>
  </xsl:param>
  <xsl:param name="admon.graphics.path"><xsl:value-of select="$webhelp.common.dir"/>images/admon/</xsl:param>
  <xsl:param name="callout.graphics.path"><xsl:value-of select="$webhelp.common.dir"/>images/callouts/</xsl:param>
  <xsl:param name="comments.php">
    <xsl:choose>
      <xsl:when test="$webhelp.war != '0' and $webhelp.war != ''">/hashcode/comments.php</xsl:when>
      <xsl:otherwise>/comments.php</xsl:otherwise>
    </xsl:choose>
  </xsl:param>
  <xsl:param name="pdfFilenameBase"/>
    <xsl:param name="includeDateInPdfFilename">
        <xsl:choose>
            <xsl:when test="$branding = 'openstack'">0</xsl:when>
            <xsl:otherwise>1</xsl:otherwise>
        </xsl:choose>
    </xsl:param>

  <xsl:param name="use.extensions">1</xsl:param>
  <xsl:param name="callouts.extension">1</xsl:param>

  <xsl:param name="project.build.directory"/>

    <xsl:param name="groupId"/>
    <xsl:param name="artifactId"/>
    <xsl:param name="docProjectVersion"/>

  <xsl:param name="feedback.email">
    <xsl:call-template name="pi-attribute">
      <xsl:with-param name="pis" select="/*/processing-instruction('rax')"/>
      <xsl:with-param name="attribute" select="'feedback.email'"/>
    </xsl:call-template>
  </xsl:param>

  <xsl:param name="glossary.collection" select="concat($project.build.directory,'/mvn/com.rackspace.cloud.api/glossary/glossary.xml')"/>

  <xsl:param name="pdf.url">
    <xsl:call-template name="pi-attribute">
      <xsl:with-param name="pis" select="/*/processing-instruction('rax')"/>
      <xsl:with-param name="attribute" select="'pdf.url'"/>
    </xsl:call-template>
  </xsl:param>
  <xsl:param name="use.id.as.filename" select="1"/>
  <xsl:param name="branding">not set</xsl:param>
  <xsl:param name="autoPdfUrl"></xsl:param>
  <xsl:param name="useLatestSuffixInPdfUrl">
    <xsl:choose>
      <xsl:when test="$branding = 'rackspace'">1</xsl:when>
      <xsl:when test="$branding = 'openstack'">0</xsl:when>
      <xsl:otherwise>0</xsl:otherwise>
    </xsl:choose>
  </xsl:param>
  <xsl:param name="section.autolabel" select="1"/>
  <xsl:param name="chapter.autolabel" select="1"/>
  <xsl:param name="appendix.autolabel" select="'A'"/>
  <xsl:param name="part.autolabel" select="'I'"/>
  <xsl:param name="reference.autolabel" select="1"/>
  <xsl:param name="qandadiv.autolabel" select="1"/>
  <xsl:param name="webhelp.autolabel" select="1"/>
  <xsl:param name="section.autolabel.max.depth" select="100"/>
  <xsl:param name="section.label.includes.component.label">
    <xsl:choose>
      <xsl:when test="$section.autolabel != '0'">1</xsl:when>
      <xsl:otherwise>0</xsl:otherwise>
    </xsl:choose>
  </xsl:param>
  <xsl:param name="component.label.includes.part.label" select="1"/>
  <xsl:param name="ignore.image.scaling" select="1"/>
  <xsl:param name="suppress.footer.navigation">1</xsl:param>
  <xsl:param name="enable.google.analytics">
    <xsl:choose>
      <xsl:when test="$branding = 'rackspace' and $security = 'external'">1</xsl:when>
      <xsl:otherwise>0</xsl:otherwise>
    </xsl:choose>
  </xsl:param>
  <xsl:param name="enable.coremetrics">
    <xsl:choose>
      <xsl:when test="$branding = 'rackspace'">1</xsl:when>
      <xsl:otherwise>0</xsl:otherwise>
    </xsl:choose>
  </xsl:param>
  <xsl:param name="google.analytics.id">
    <xsl:choose>
      <xsl:when test="$branding = 'rackspace'">UA-23102455-4</xsl:when>
      <xsl:otherwise/>
    </xsl:choose>
  </xsl:param>
  <xsl:param name="coremetrics.id">
    <xsl:choose>
      <xsl:when test="$branding = 'rackspace'">90378909</xsl:when>
      <xsl:otherwise/>
    </xsl:choose>
  </xsl:param>
  <xsl:param name="google.analytics.domain">
    <xsl:choose>
      <xsl:when test="$branding = 'rackspace'">.rackspace.com</xsl:when>
      <xsl:when test="$branding = 'openstack'">.openstack.org</xsl:when>
      <xsl:when test="$branding = 'repose'">.openrepose.org</xsl:when>
      <xsl:otherwise/>
    </xsl:choose>
  </xsl:param>

  <xsl:param name="security">external</xsl:param>
  <xsl:param name="draft.status" select="''"/>
  <xsl:param name="root.attr.status"><xsl:if test="$draft.status = 'on' or (/*[@status = 'draft'] and $draft.status = '')">draft;</xsl:if></xsl:param>
  <xsl:param name="profile.security">
    <xsl:choose>
      <xsl:when test="$security = 'external'"><xsl:value-of select="$root.attr.status"/>external</xsl:when>
      <xsl:when test="$security = 'internal'"><xsl:value-of select="$root.attr.status"/>internal</xsl:when>
      <xsl:when test="$security = 'reviewer'"><xsl:value-of select="$root.attr.status"/>reviewer;internal;external</xsl:when>
      <xsl:when test="$security = 'writeronly'"><xsl:value-of select="$root.attr.status"/>reviewer;internal;external;writeronly</xsl:when>
      <xsl:when test="$security = 'external'"><xsl:value-of select="$root.attr.status"/>external</xsl:when>
      <xsl:otherwise>
	<xsl:message terminate="yes"> 
	  ERROR: The value "<xsl:value-of select="$security"/>" is not valid for the security paramter. 
	         Valid values are: external, internal, reviewer, and writeronly. 
	</xsl:message>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:param>
  <xsl:param name="show.comments">
    <xsl:choose>
      <xsl:when test="$security = 'reviewer' or $security = 'writeronly'">1</xsl:when>
      <xsl:otherwise>0</xsl:otherwise>
    </xsl:choose>
  </xsl:param>
  
<xsl:param name="generate.toc">
appendix  toc,title
article/appendix  nop
article   toc,title
book      title,figure,table,example,equation
chapter   toc,title
part      toc,title
preface   toc,title
qandadiv  toc
qandaset  toc
reference toc,title
sect1     toc
sect2     toc
sect3     toc
sect4     toc
sect5     toc
section   toc
set       toc,title
</xsl:param>

  <xsl:param name="enable.disqus">0</xsl:param>
  <xsl:param name="disqus_identifier" select="/*/@xml:id"/>
  <xsl:param name="disqus.shortname">
    <xsl:choose>
      <xsl:when test="$branding = 'test'">jonathan-test-dns</xsl:when>
      <xsl:when test="$branding = 'rackspace'">rc-api-docs</xsl:when>
      <xsl:when test="$branding = 'openstack'">openstackdocs</xsl:when>
      <xsl:when test="$branding = 'openstackextension'">openstackdocs</xsl:when>
    </xsl:choose>
      
  </xsl:param>
    
  <xsl:param name="brandname">
    <xsl:choose>
      <xsl:when test="$branding = 'openstack'">OpenStack</xsl:when>
      <xsl:when test="$branding = 'repose'">Repose</xsl:when>
      <xsl:when test="$branding = 'openstackextension'">OpenStack Extension</xsl:when>
      <xsl:otherwise>Rackspace</xsl:otherwise>
    </xsl:choose>
  </xsl:param>
  <xsl:param name="main.docs.url">
    <xsl:choose>
      <xsl:when test="$branding = 'openstack'">http://docs.openstack.org/</xsl:when>
      <xsl:when test="$branding = 'repose'">http://openrepose.org/documentation.html</xsl:when>
      <xsl:when test="$branding = 'openstackextension'">http://docs-beta.rackspace.com/test/jonathan/OpenstackExtDocs/</xsl:when>
      <xsl:otherwise>
	<xsl:choose>
	  <xsl:when test="$webhelp.war != '' and $webhelp.war != '0'">/</xsl:when>
	  <xsl:otherwise>http://docs.rackspace.com/api/</xsl:otherwise>
	</xsl:choose>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:param>
  
  <xsl:param name="use.version.for.disqus">0</xsl:param>
    <xsl:variable name="version.for.disqus">
        <xsl:choose>
            <xsl:when test="$use.version.for.disqus!='0'">
              <xsl:value-of select="translate(/*/d:info/d:releaseinfo[1],' ','')"/>
            </xsl:when>
        <xsl:otherwise></xsl:otherwise>
        </xsl:choose>       
    </xsl:variable>
    
    <xsl:param name="use.disqus.id">1</xsl:param>
    
	<xsl:param name="social.icons">0</xsl:param>
    <xsl:param name="legal.notice.url">index.html</xsl:param>
	<xsl:include href="../inline.xsl"/>

    <xsl:template name="user.footer.content">
        <xsl:if test="$enable.disqus!='0' and (//d:section[not(@xml:id)] or //d:chapter[not(@xml:id)] or //d:part[not(@xml:id)] or //d:appendix[not(@xml:id)] or //d:preface[not(@xml:id)] or /*[not(@xml:id)])">
            <xsl:message terminate="yes"> 
                <xsl:for-each select="//d:section[not(@xml:id)]|//d:chapter[not(@xml:id)]|//d:part[not(@xml:id)]|//d:appendix[not(@xml:id)]|//d:preface[not(@xml:id)]|/*[not(@xml:id)]">
                    ERROR: The <xsl:value-of select="local-name()"/> "<xsl:value-of select=".//d:title[1]"/>" is missing an id.
                </xsl:for-each>
                     When Disqus comments are enabled, the root element and every part, chapter, appendix, preface, and section must have an xml:id attribute.
            </xsl:message>
        </xsl:if>
        
	<!-- Alternate location for SyntaxHighlighter scripts -->


        <script type="text/javascript" src="{$webhelp.common.dir}main.js">
            <xsl:comment></xsl:comment>
        </script>
	
	<xsl:if test="$enable.disqus != '0'">
	  <hr />
	      <xsl:choose>
		<xsl:when test="$enable.disqus = 'intranet'">
          <xsl:if test="$feedback.email =''">
              <xsl:message terminate="yes">
ERROR: Feedback email not set but internal comments are enabled.
              </xsl:message>
          </xsl:if>
		  <script language="JavaScript" src="{$comments.php}?email={$feedback.email}" type="text/javascript"><xsl:comment/></script>
		  <noscript>You must have JavaScript enabled to view and post comments.</noscript>
		</xsl:when>
		<xsl:otherwise>

	  <div id="disqus_thread">
	    <script type="text/javascript">
	      if(window.location.protocol.substring(0,4) == 'http'){
	        var disqus_shortname = '<xsl:value-of select="$disqus.shortname"/>';
	      <xsl:if test="$use.disqus.id != '0'">
	        var disqus_identifier = '<xsl:value-of select="$disqus_identifier"/><xsl:value-of select="$version.for.disqus"/><xsl:value-of select="@xml:id"/>';
	      </xsl:if>
	      }
	    </script>
	    <noscript>Please enable JavaScript to view the <a href="http://disqus.com/?ref_noscript">comments powered by Disqus.</a></noscript>
	    <script type="text/javascript" src="{$webhelp.common.dir}comments.js"><xsl:comment/></script>
	  </div>	  
		</xsl:otherwise>
	      </xsl:choose>
	</xsl:if>
	<hr/>
	<div class="legal"><a href="{$legal.notice.url}">Legal notices</a></div>

    </xsl:template>

    <xsl:template name="breadcrumbs">
      <xsl:param name="home"/>
      <xsl:variable name="pubdate"><xsl:if test="not($security = 'external') and not($security = '') and $pdfFilenameBase = ''">-<xsl:value-of select="$security"/></xsl:if><xsl:if test="/*/d:info/d:pubdate and $includeDateInPdfFilename = '1'"><xsl:value-of select="concat('-',translate(/*/d:info/d:pubdate,'-',''))"/></xsl:if></xsl:variable>
      <p class="breadcrumbs"><a href="{$main.docs.url}"><xsl:value-of select="$brandname"/> Manuals</a>  <a><xsl:attribute name="href">
      <xsl:call-template name="href.target">
	<xsl:with-param name="object" select="$home"/>
      </xsl:call-template>
      </xsl:attribute><xsl:value-of select="normalize-space(//d:title[1])"/><xsl:apply-templates select="/*/d:info/d:releaseinfo[1]" mode="rackspace-title"/></a> 
      </p> 
      <xsl:choose>
      	<xsl:when test="normalize-space($autoPdfUrl) != '' and $useLatestSuffixInPdfUrl = '0'">
      		<a onclick="_gaq.push(['_trackEvent', 'Header', 'pdfDownload', 'click', 1]);" alt="Download a pdf of this document" class="pdficon" href="{concat(normalize-space(substring($autoPdfUrl,1,string-length($autoPdfUrl) - 3)), $pubdate,'.pdf')}"><img src="{$webhelp.common.dir}images/pdf.png"/></a>
      	</xsl:when>
      	<xsl:when test="normalize-space($autoPdfUrl) != ''">
      		<a onclick="_gaq.push(['_trackEvent', 'Header', 'pdfDownload', 'click', 1]);" alt="Download a pdf of this document" class="pdficon" href="{normalize-space(substring($autoPdfUrl,1,string-length($autoPdfUrl) - 3))}-latest.pdf"><img src="{$webhelp.common.dir}images/pdf.png"/></a>
      	</xsl:when>
      	<xsl:when test="normalize-space($pdf.url) != '' and not(normalize-space($autoPdfUrl) != '')">
      		<a onclick="_gaq.push(['_trackEvent', 'Header', 'pdfDownload', 'click', 1]);" alt="Download a pdf of this document" class="pdficon" href="{normalize-space($pdf.url)}"><img src="{$webhelp.common.dir}images/pdf.png"/></a>
      	</xsl:when>
      </xsl:choose>
    <xsl:if test="//d:revhistory/d:revision and $canonical.url.base != ''">
      &#160;
      <a href="../atom.xml"><img alt="Atom feed of this document" src="{$webhelp.common.dir}images/feed-icon.png"/></a>
    </xsl:if>
    <xsl:if test="$social.icons != '0' and $security = 'external' ">
<!--social buttons-->
<div id="fb-root">&#160;</div><script src="http://connect.facebook.net/en_US/all.js#xfbml=1"><xsl:comment> </xsl:comment></script>
<script>(function(d, s, id) {
  var js, fjs = d.getElementsByTagName(s)[0];
  if (d.getElementById(id)) return;
  js = d.createElement(s); js.id = id;
  js.src = "//connect.facebook.net/en_US/all.js#xfbml=1";
  fjs.parentNode.insertBefore(js, fjs);
}(document, 'script', 'facebook-jssdk'));</script>
<!-- Place this render call where appropriate  for google +1 button-->
<script type="text/javascript">
  (function() {
    var po = document.createElement('script'); po.type = 'text/javascript'; po.async = true;
    po.src = 'https://apis.google.com/js/plusone.js';
    var s = document.getElementsByTagName('script')[0]; s.parentNode.insertBefore(po, s);
  })();
</script>
<style>
.fb_edge_comment_widget {
    margin-left: -280px;
}
.fb-like{vertical-align:text-top;position:absolute;top:.5em;right:311px}
#gplusone{display:inline;position:absolute;right:410px;top:.5em}
#rstwitter{vertical-align:text-top;display:inline;position:absolute;right:450px;top:.5em}
</style>
 <xsl:comment><xsl:text>[if IE]>
	&lt;style>
#gplusone{top:0em}
#rstwitter{top:-.15em}
.fb-like{top:-.5em}
&lt;/style>&lt;![endif]</xsl:text></xsl:comment><script type="text/javascript">_ga.trackFacebook();</script>
<div class="fb-like" data-send="false" data-width="50" data-show-faces="false" data-layout="button_count" data-font="arial" > &#160; </div>      
<!-- Place this tag where you want the +1 button to render -->
<div id="gplusone" >
<g:plusone size="medium" annotation="none"></g:plusone>
</div>
<div id="rstwitter">
<a href="https://twitter.com/share" class="twitter-share-button" data-text="Check out this Rackspace documentation page:" data-lang="en" data-count="none">Tweet</a>
<script>!function(d,s,id){var js,fjs=d.getElementsByTagName(s)[0];if(!d.getElementById(id)){js=d.createElement(s);js.id=id;js.src="//platform.twitter.com/widgets.js";fjs.parentNode.insertBefore(js,fjs);}}(document,"script","twitter-wjs");</script>      
</div> <!--end social buttons -->
    </xsl:if>
    </xsl:template>

      <xsl:template name="webhelpheader">
        <xsl:param name="prev"/>
        <xsl:param name="next"/>
        <xsl:param name="nav.context"/>
        
        <xsl:variable name="home" select="/*[1]"/>
        <xsl:variable name="up" select="parent::*"/>
        
        <div id="header">
	  <a onclick="_gaq.push(['_trackEvent', 'Header', 'logo', 'click', 1]);" target="_blank">
	    <xsl:attribute name="href">
	    <xsl:choose>
		<xsl:when test="$branding = 'openstack'">http://www.openstack.org</xsl:when>
		<xsl:when test="$branding = 'repose'">http://www.openrepose.org</xsl:when>
	    <xsl:when test="$branding = 'openstackextension'">http://docs-beta.rackspace.com/test/jonathan/OpenStackExtDocs/</xsl:when>
		<xsl:otherwise>http://www.rackspace.com</xsl:otherwise>
	      </xsl:choose>
	    </xsl:attribute>
	    <img src='{$webhelp.common.dir}images/{$branding}-logo.png' alt="{$brandname} Documentation" width="157" height="47" />
	  </a>
	  <!-- <xsl:if test="$branding = 'openstack' or $branding = 'openstackextension'"> -->
	  <!--   <xsl:call-template name="breadcrumbs"> -->
	  <!--     <xsl:with-param name="home" select="$home"/> -->
	  <!--   </xsl:call-template> -->
	  <!-- </xsl:if> -->
            <!-- Display the page title and the main heading(parent) of it-->
            <h1>
                <xsl:apply-templates select="." mode="object.title.markup"/>
             </h1>
            
            <!-- Prev and Next links generation-->
            <div id="navheader" align="right">
                <xsl:comment>
                    <!-- KEEP this code. In case of neither prev nor next links are available, this will help to
                        keep the integrity of the DOM tree-->
                </xsl:comment>
                <!--xsl:with-param name="prev" select="$prev"/>
                    <xsl:with-param name="next" select="$next"/>
                    <xsl:with-param name="nav.context" select="$nav.context"/-->
                <table class="navLinks">
                    <tr>
                        <td>
                            <a id="showHideButton" onclick="showHideToc(); _gaq.push(['_trackEvent', 'Header', 'show/hide', 'click', 1]);"
                                class="pointLeft" title="Hide TOC tree">Sidebar
                            </a>
                        </td>
                        <xsl:if test="count($prev) &gt; 0
                            or (count($up) &gt; 0
                            and generate-id($up) != generate-id($home)
                            and $navig.showtitles != 0)
                            or count($next) &gt; 0">
                            <td>
                                <xsl:if test="count($prev)>0">
                                    <a accesskey="p" class="navLinkPrevious" onclick="_gaq.push(['_trackEvent', 'Header', 'prevLink', 'click', 1]);" tabindex="5">
                                        <xsl:attribute name="href">
                                            <xsl:call-template name="href.target">
                                                <xsl:with-param name="object" select="$prev"/>
                                            </xsl:call-template>
                                        </xsl:attribute>
                                        <xsl:call-template name="navig.content">
                                            <xsl:with-param name="direction" select="'prev'"/>
                                        </xsl:call-template>
                                    </a>
                                </xsl:if>
                                
                                <!-- "Up" link-->
                                <xsl:choose>
                                    <xsl:when test="count($up)&gt;0
                                        and generate-id($up) != generate-id($home)">
				      |
                                        <a accesskey="u" class="navLinkUp" onclick="_gaq.push(['_trackEvent', 'Header', 'upLink', 'click', 1]);" tabindex="5">
                                            <xsl:attribute name="href">
                                                <xsl:call-template name="href.target">
                                                    <xsl:with-param name="object" select="$up"/>
                                                </xsl:call-template>
                                            </xsl:attribute>
                                            <xsl:call-template name="navig.content">
                                                <xsl:with-param name="direction" select="'up'"/>
                                            </xsl:call-template>
                                        </a>
                                    </xsl:when>
                                    <xsl:otherwise>&#160;</xsl:otherwise>
                                </xsl:choose>
                                
                                <xsl:if test="count($next)>0">
				  |
                                    <a accesskey="n" class="navLinkNext" onclick="_gaq.push(['_trackEvent', 'Header', 'nextLink', 'click', 1]);" tabindex="5">
                                        <xsl:attribute name="href">
                                            <xsl:call-template name="href.target">
                                                <xsl:with-param name="object" select="$next"/>
                                            </xsl:call-template>
                                        </xsl:attribute>
                                        <xsl:call-template name="navig.content">
                                            <xsl:with-param name="direction" select="'next'"/>
                                        </xsl:call-template>
                                    </a>
                                </xsl:if>
                            </td>
                        </xsl:if>
                        
                    </tr>
                </table>                
            </div>            
        </div>

	<!-- <xsl:if test="$branding = 'rackspace'"> -->
	  <div id="toolbar" class="ui-tabs-nav ui-helper-reset ui-helper-clearfix ui-widget-header ui-corner-all">
	    <div id="toolbar-left">
	      <xsl:call-template name="breadcrumbs">
		<xsl:with-param name="home" select="$home"/>
	      </xsl:call-template>
	    </div>
	  </div>
	<!-- </xsl:if> -->
	<!-- <xsl:if test="$branding = 'openstackextension'"> -->
	<!--   <div id="toolbar" class="ui-tabs-nav ui-helper-reset ui-helper-clearfix ui-widget-header ui-corner-all"> -->
	<!--     <div id="toolbar-left"> -->
	<!--       <xsl:call-template name="breadcrumbs"> -->
	<!-- 	<xsl:with-param name="home" select="$home"/> -->
	<!--       </xsl:call-template> -->
	<!--     </div> -->
	<!--   </div> -->
	<!-- </xsl:if> -->
    </xsl:template>
    
    <xsl:template name="webhelptoc">
        <xsl:param name="currentid"/>
        <xsl:choose>
            <xsl:when test="$rootid != ''">
                <xsl:variable name="title">
                    <xsl:if test="$webhelp.autolabel=1">
                        <xsl:variable name="label.markup">
                            <xsl:apply-templates select="key('id',$rootid)" mode="label.markup"/>
                        </xsl:variable>
                        <xsl:if test="normalize-space($label.markup)">
                            <xsl:value-of select="concat($label.markup,$autotoc.label.separator)"/>
                        </xsl:if>
                    </xsl:if>
                    <xsl:apply-templates select="key('id',$rootid)" mode="title.markup"/>
                </xsl:variable>
                <xsl:variable name="href">
                    <xsl:choose>
                        <xsl:when test="$manifest.in.base.dir != 0">
                            <xsl:call-template name="href.target">
                                <xsl:with-param name="object" select="key('id',$rootid)"/>
                            </xsl:call-template>
                        </xsl:when>
                        <xsl:otherwise>
                            <xsl:call-template name="href.target.with.base.dir">
                                <xsl:with-param name="object" select="key('id',$rootid)"/>
                            </xsl:call-template>
                        </xsl:otherwise>
                    </xsl:choose>
                </xsl:variable>
            </xsl:when>
            
            <xsl:otherwise>
                <xsl:variable name="title">
                    <xsl:if test="$webhelp.autolabel=1">
                        <xsl:variable name="label.markup">
                            <xsl:apply-templates select="/*" mode="label.markup"/>
                        </xsl:variable>
                        <xsl:if test="normalize-space($label.markup)">
                            <xsl:value-of select="concat($label.markup,$autotoc.label.separator)"/>
                        </xsl:if>
                    </xsl:if>
                    <xsl:apply-templates select="/*" mode="title.markup"/>
                </xsl:variable>
                <xsl:variable name="href">
                    <xsl:choose>
                        <xsl:when test="$manifest.in.base.dir != 0">
                            <xsl:call-template name="href.target">
                                <xsl:with-param name="object" select="/"/>
                            </xsl:call-template>
                        </xsl:when>
                        <xsl:otherwise>
                            <xsl:call-template name="href.target.with.base.dir">
                                <xsl:with-param name="object" select="/"/>
                            </xsl:call-template>
                        </xsl:otherwise>
                    </xsl:choose>
                </xsl:variable>
                
                <div>
                    <div id="leftnavigation" style="padding-top:3px; background-color:white;">
                        <div id="tabs">
                            <ul>
                                <li>
                                    <a href="#treeDiv" tabindex="1">
                                        <span class="contentsTab">
                                            <xsl:call-template name="gentext">
                                                <xsl:with-param name="key" select="'TableofContents'"/>
                                            </xsl:call-template>
                                        </span>
                                    </a>
                                </li>
                                <xsl:if test="$webhelp.include.search.tab != 'false'">
                                    <li>
                                        <a href="#searchDiv" tabindex="1">
                                            <span class="searchTab">
                                                <xsl:call-template name="gentext">
                                                    <xsl:with-param name="key" select="'Search'"/>
                                                </xsl:call-template>
                                            </span>
                                        </a>
                                    </li>
                                </xsl:if>
                            </ul>
                            <div id="treeDiv">
                                <img src="{$webhelp.common.dir}images/loading.gif" alt="loading table of contents..."
                                    id="tocLoading" style="display:block;"/>
                                <div id="ulTreeDiv" style="display:none" class="thisisthat">
                                    <ul id="tree" class="filetree">
                                        <xsl:apply-templates select="/*/*" mode="webhelptoc">
                                            <xsl:with-param name="currentid" select="$currentid"/>
                                        </xsl:apply-templates>
                                    </ul>
                                </div>
                                
                            </div>
                            <xsl:if test="$webhelp.include.search.tab != 'false'">
                                <div id="searchDiv">
                                    <div id="search">
                                        <form onsubmit="Verifie(ditaSearch_Form);return false"
                                            name="ditaSearch_Form"
                                            class="searchForm">
                                            <fieldset class="searchFieldSet">
                                                <legend>
                                                    <xsl:call-template name="gentext">
                                                        <xsl:with-param name="key" select="'Search'"/>
                                                    </xsl:call-template>
                                                </legend>
                                                <center>
                                                    <input id="textToSearch" name="textToSearch" type="text"
                                                        class="searchText"/>
                                                    <xsl:text disable-output-escaping="yes"> <![CDATA[&nbsp;]]> </xsl:text>
                                                    <input onclick="Verifie(ditaSearch_Form)" type="button"
                                                        class="searchButton"
                                                        value="Go" id="doSearch"/>
                                                </center>
                                            </fieldset>
                                        </form>
                                    </div>
                                    <div id="searchResults">
                                        <center> </center>
                                    </div>
                                    <p class="searchHighlight"><a href="#" onclick="toggleHighlight()">Search Highlighter (On/Off)</a></p>
                                </div>
                            </xsl:if>
                            
                        </div>
                    </div>
                </div>
            </xsl:otherwise>
        </xsl:choose>
    </xsl:template>
    
      <xsl:template match="d:glossterm[not(parent::d:glossentry)]">
        <xsl:variable name="term"><xsl:value-of select="."/></xsl:variable>
        <xsl:variable name="definition">
	  <strong><xsl:value-of select="$term"/>: </strong>
            <xsl:choose>
                <xsl:when test="@linkend and //d:glossentry[@xml:id = current()/@linkend]">
                    <xsl:apply-templates select="//d:glossentry[@xml:id = current()/@linkend]/d:glossdef" mode="make-definition"/>    
                </xsl:when>
		<xsl:when test="@linkend and not($glossary.collection = '') and document($glossary.collection,.)//d:glossentry[@xml:id = current()/@linkend]">
                    <xsl:apply-templates select="document($glossary.collection,.)//d:glossentry[@xml:id = current()/@linkend]/d:glossdef" mode="make-definition"/>    
		</xsl:when>
                <xsl:when test="//d:glossentry[d:glossterm = $term]">
                    <xsl:apply-templates select="//d:glossentry[d:glossterm = $term]/d:glossdef" mode="make-definition"/>    
                </xsl:when>
		<xsl:when test="not($glossary.collection = '') and document($glossary.collection,.)//d:glossentry[d:glossterm = $term]">
                    <xsl:apply-templates select="document($glossary.collection,.)//d:glossentry[d:glossterm = $term]/d:glossdef" mode="make-definition"/>    
		</xsl:when>
                <xsl:when test="//d:glossentry[d:glossterm = current()/@baseform]">
                    <xsl:apply-templates select="//d:glossentry[d:glossterm = current()/@baseform]/d:glossdef" mode="make-definition"/>    
                </xsl:when>
                <xsl:when test="not($glossary.collection = '') and document($glossary.collection,.)//d:glossentry[d:glossterm = current()/@baseform]">
                    <xsl:apply-templates select="document($glossary.collection,.)//d:glossentry[d:glossterm = current()/@baseform]/d:glossdef" mode="make-definition"/>    
                </xsl:when>
		<xsl:otherwise>
                    <xsl:message>
                        No definition found for <xsl:copy-of select="."/>                    
                    </xsl:message>		    
		</xsl:otherwise>
            </xsl:choose>
            </xsl:variable>
        <xsl:variable name="displayDefinition">
	  <strong><xsl:value-of select="$term"/>:</strong><xsl:text> </xsl:text>
	  <xsl:apply-templates select="$definition/d:glossdef/*"/>
        </xsl:variable>
             <script>
             $(document).ready(function(){
               $("a.gloss#<xsl:value-of select="translate($term,' ','_')"/>").qtip({
               content: '<xsl:copy-of select='$displayDefinition'/>',
               show: {event:'mouseover',delay:500},
               hide: {event:'mouseout',delay:500, fixed:true},
               style: { 
                        width: 200,
                        padding: 5,
                        background: '#FFFFCC',
                        color: 'black',
                        textAlign: 'left',
                        border: {
                                    width: 1,
                                    radius: 4,
                                    color: '#EEEEBB'
                        },
                        tip: true,
                        name: 'cream' // Inherit the rest of the attributes from the preset cream style
                },
                position: {
                    corner: {
                            target: 'topMiddle',
                            tooltip: 'bottomLeft'
                    }
                }
               });
             });
             </script>
    
        <a class="gloss" href="#"><xsl:attribute name="id"><xsl:value-of select="translate($term,' ','_')"></xsl:value-of></xsl:attribute> <xsl:value-of select="."/></a>
    </xsl:template>
    
    <xsl:template match="* | comment() | processing-instruction() | @*" mode="make-definition">
        <xsl:copy>
	  <xsl:apply-templates select="node() | @*" mode="make-definition"/>
        </xsl:copy>
    </xsl:template>
    
    <xsl:template match="text()" name="escape-javascript" mode="make-definition">
        <xsl:param name="string" select="."/>
        <xsl:choose>
            <xsl:when test='contains($string, "&apos;")'>
                <xsl:call-template name="escape-javascript">
                    <xsl:with-param name="string"
                        select='substring-before($string, "&apos;")' />
                </xsl:call-template>
                <xsl:text>\'</xsl:text>
                <xsl:call-template name="escape-javascript">
                    <xsl:with-param name="string"
                        select='substring-after($string, "&apos;")' />
                </xsl:call-template>
            </xsl:when>
            <xsl:when test="contains($string, '&#xA;')">
                <xsl:call-template name="escape-javascript">
                    <xsl:with-param name="string"
                        select="substring-before($string, '&#xA;')" />
                </xsl:call-template>
                <xsl:text> </xsl:text>
                <xsl:call-template name="escape-javascript">
                    <xsl:with-param name="string"
                        select="substring-after($string, '&#xA;')" />
                </xsl:call-template>
            </xsl:when>
            <xsl:when test="contains($string, '\')">
                <xsl:value-of select="substring-before($string, '\')" />
                <xsl:text>\\</xsl:text>
                <xsl:call-template name="escape-javascript">
                    <xsl:with-param name="string"
                        select="substring-after($string, '\')" />
                </xsl:call-template>
            </xsl:when>
            <xsl:otherwise><xsl:value-of select="$string" /></xsl:otherwise>
        </xsl:choose>
    </xsl:template>
    
    <!-- The following templates change the color of text flagged as reviewer, internal, or writeronly -->    
    <xsl:template match="text()[ contains(concat(';',ancestor::*/@security,';'),';internal;') and not(ancestor::d:programlisting) ] | xref[ contains(concat(';',ancestor::*/@security,';'),';internal;') and not(ancestor::d:programlisting)]"><span class="internal"><xsl:apply-imports/></span></xsl:template>
    <xsl:template match="text()[ contains(concat(';',ancestor::*/@security,';'),';writeronly;') and not(ancestor::d:programlisting) ] | xref[ contains(concat(';',ancestor::*/@security,';'),';writeronly;') and not(ancestor::d:programlisting)]"><span class="writeronly"><xsl:apply-imports/></span></xsl:template>
    <xsl:template match="text()[ contains(concat(';',ancestor::*/@security,';'),';reviewer;') and not(ancestor::d:programlisting) ] | xref[ contains(concat(';',ancestor::*/@security,';'),';reviewer;') and not(ancestor::d:programlisting)]"><span class="remark"><xsl:apply-imports/></span></xsl:template>
    <xsl:template match="text()[ ancestor::*/@role = 'highlight' and not(ancestor::d:programlisting) ] | xref[ ancestor::*/@role = 'highlight' and not(ancestor::d:programlisting)]" priority="10"><span class="remark"><xsl:apply-imports/></span></xsl:template>

    <xsl:template match="d:parameter[@role = 'template']">
      <xsl:param name="content">
	<xsl:call-template name="anchor"/>
	<xsl:call-template name="simple.xlink">
	  <xsl:with-param name="content">
	    <xsl:apply-templates/>
	  </xsl:with-param>
	</xsl:call-template>
      </xsl:param>
      <em><xsl:call-template name="common.html.attributes"/><code><xsl:call-template name="generate.html.title"/><xsl:call-template name="dir"/>{<xsl:copy-of select="$content"/>}<xsl:call-template name="apply-annotations"/></code></em>
    </xsl:template>

<!-- The following two templates are from the svn trunk (html.xsl) -->
<!-- Remove them once we've upgraded to use a version -->
<!-- of the base xsls that is greater than 1.76.1 -->
<xsl:template match="*" mode="common.html.attributes">
  <xsl:param name="class" select="local-name(.)"/>
  <xsl:param name="inherit" select="0"/>
  <xsl:call-template name="generate.html.lang"/>
  <xsl:call-template name="dir">
    <xsl:with-param name="inherit" select="$inherit"/>
  </xsl:call-template>
  <xsl:apply-templates select="." mode="class.attribute">
    <xsl:with-param name="class" select="$class"/>
  </xsl:apply-templates>
</xsl:template>

<xsl:template match="*" mode="locale.html.attributes">
  <xsl:call-template name="generate.html.lang"/>
  <xsl:call-template name="dir"/>
</xsl:template>
<!-- End stuff from svn trunk -->

  <xsl:template name="badMatch">
    <span style="color: red">this?</span>
  </xsl:template>


<xsl:template match="d:sidebar/d:title">
  <b><xsl:apply-templates/></b>
</xsl:template>

<xsl:template name="anchor">
  <xsl:param name="node" select="."/>
  <xsl:param name="conditional" select="1"/>
  <xsl:variable name="id">
    <xsl:call-template name="object.id">
      <xsl:with-param name="object" select="$node"/>
    </xsl:call-template>
  </xsl:variable>
  <xslo:if xmlns:xslo="http://www.w3.org/1999/XSL/Transform" test="not($node[parent::d:blockquote])"><xsl:if test="$conditional = 0 or $node/@id or $node/@xml:id">
    <!-- Do not close this a tag because it causes problems in older version of Firefox (pre 4.0) in conjunction with the SyntaxHighlighter we're using. -->
    <a id="{$id}">&#160;</a>
  </xsl:if></xslo:if>
</xsl:template>


    <xsl:template name="basename">
        <xsl:param name="filename" select="''"></xsl:param>
        <xsl:choose>
        <xsl:when test="contains($filename, '/')">
            <xsl:call-template name="basename">
                <xsl:with-param name="filename" select="substring-after($filename, '/')"></xsl:with-param>
            </xsl:call-template>
        </xsl:when>
        <xsl:when test="contains($filename, '.')">
            <xsl:call-template name="basename">
                <xsl:with-param name="filename">
                    <xsl:value-of select="substring-before($filename,'.')"/><xsl:if test="contains(substring-after($filename,'.'),'.')">*</xsl:if>
                </xsl:with-param>
            </xsl:call-template>
        </xsl:when>    
        <xsl:otherwise><xsl:value-of select="translate($filename,'*','.')"/></xsl:otherwise>
        </xsl:choose>
    </xsl:template>

</xsl:stylesheet>
